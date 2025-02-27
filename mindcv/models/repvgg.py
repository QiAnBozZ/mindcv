"""
MindSpore implementation of `RepVGG`.
Refer to RepVGG: Making VGG_style ConvNets Great Again
"""

import copy
import numpy as np

import mindspore.nn as nn
import mindspore.ops as ops
import mindspore.common.initializer as init
from mindspore import Tensor, save_checkpoint

from .layers import Identity, SqueezeExcite, GlobalAvgPooling
from .utils import load_pretrained
from .registry import register_model


def _cfg(url='', **kwargs):
    return {
        'url': url,
        'num_classes': 1000,
        'first_conv': '', 'classifier': '',
        **kwargs
    }


default_cfgs = {
    'RepVGG-A0': _cfg(url=''),
}


def conv_bn(in_channels: int, out_channels: int, kernel_size: int,
            stride: int, padding: int, group: int = 1) -> nn.SequentialCell:
    cell = nn.SequentialCell([
        nn.Conv2d(in_channels=in_channels, out_channels=out_channels,
                  kernel_size=kernel_size, stride=stride, padding=padding, group=group, pad_mode="pad",
                  has_bias=False),
        nn.BatchNorm2d(num_features=out_channels)
    ])
    return cell


class RepVGGBlock(nn.Cell):
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int,
                 stride: int = 1, padding: int = 0, dilation: int = 1,
                 group: int = 1, padding_mode: str = 'zeros',
                 deploy: bool = False, use_se: bool = False) -> None:
        super(RepVGGBlock, self).__init__()
        self.deploy = deploy
        self.group = group
        self.in_channels = in_channels

        assert kernel_size == 3
        assert padding == 1

        padding_11 = padding - kernel_size // 2

        self.nonlinearity = nn.ReLU()

        if use_se:
            self.se = SqueezeExcite(
                in_channels=out_channels, rd_channels=out_channels // 16)
        else:
            self.se = Identity()

        if deploy:
            self.rbr_reparam = nn.Conv2d(in_channels=in_channels, out_channels=out_channels, kernel_size=kernel_size,
                                         stride=stride, padding=padding, dilation=dilation, group=group, bias=True,
                                         padding_mode=padding_mode)
        else:
            self.rbr_reparam = None
            self.rbr_identity = nn.BatchNorm2d(
                num_features=in_channels) if out_channels == in_channels and stride == 1 else None

            self.rbr_dense = conv_bn(in_channels=in_channels, out_channels=out_channels, kernel_size=kernel_size,
                                     stride=stride, padding=padding, group=group)
            self.rbr_1x1 = conv_bn(in_channels=in_channels, out_channels=out_channels, kernel_size=1, stride=stride,
                                   padding=padding_11, group=group)

    def construct(self, inputs: Tensor) -> Tensor:
        if self.rbr_reparam is not None:
            return self.nonlinearity(self.se(self.rbr_reparam(inputs)))

        if self.rbr_identity is None:
            id_out = 0
        else:
            id_out = self.rbr_identity(inputs)

        return self.nonlinearity(self.se(self.rbr_dense(inputs) + self.rbr_1x1(inputs) + id_out))

    def get_custom_L2(self):
        K3 = self.rbr_dense.conv.weight
        K1 = self.rbr_1x1.conv.weight

        t3 = self.rbr_dense.bn.weight / (
            ops.sqrt((self.rbr_dense.bn.moving_variance + self.rbr_dense.bn.eps)))
        t3 = ops.reshape(t3, (-1, 1, 1, 1))

        t1 = (self.rbr_1x1.bn.weight /
              ((self.rbr_1x1.bn.moving_variance + self.rbr_1x1.bn.eps).sqrt()))
        t1 = ops.reshape(t1, (-1, 1, 1, 1))

        l2_loss_circle = ops.reduce_sum(
            K3 ** 2) - ops.reduce_sum(K3[:, :, 1:2, 1:2] ** 2)
        eq_kernel = K3[:, :, 1:2, 1:2] * t3 + K1 * t1
        l2_loss_eq_kernel = ops.reduce_sum(
            eq_kernel ** 2 / (t3 ** 2 + t1 ** 2))
        return l2_loss_eq_kernel + l2_loss_circle

    #   This func derives the equivalent kernel and bias in a DIFFERENTIABLE way.
    #   You can get the equivalent kernel and bias at any time and do whatever you want,
    #   for example, apply some penalties or constraints during training, just like you do to the other models.
    #   May be useful for quantization or pruning.
    def get_equivalent_kernel_bias(self):
        kernel3x3, bias3x3 = self._fuse_bn_tensor(self.rbr_dense)
        kernel1x1, bias1x1 = self._fuse_bn_tensor(self.rbr_1x1)
        kernelid, biasid = self._fuse_bn_tensor(self.rbr_identity)
        return kernel3x3 + self._pad_1x1_to_3x3_tensor(kernel1x1) + kernelid, bias3x3 + bias1x1 + biasid

    def _pad_1x1_to_3x3_tensor(self, kernel1x1):
        if kernel1x1 is None:
            return 0
        return ops.pad(kernel1x1, ((1, 1), (1, 1)))

    def _fuse_bn_tensor(self, branch):
        if branch is None:
            return 0, 0
        if isinstance(branch, nn.SequentialCell):
            kernel = branch.conv.weight
            moving_mean = branch.bn.moving_mean
            moving_variance = branch.bn.moving_variance
            gamma = branch.bn.gamma
            beta = branch.bn.beta
            eps = branch.bn.eps
        else:
            assert isinstance(branch, (nn.BatchNorm2d, nn.SyncBatchNorm))
            if not hasattr(self, 'id_tensor'):
                input_dim = self.in_channels // self.group
                kernel_value = np.zeros(
                    (self.in_channels, input_dim, 3, 3), dtype=np.float32)
                for i in range(self.in_channels):
                    kernel_value[i, i % input_dim, 1, 1] = 1
                self.id_tensor = Tensor(
                    kernel_value, dtype=branch.weight.dtype)
            kernel = self.id_tensor
            moving_mean = branch.moving_mean
            moving_variance = branch.moving_variance
            gamma = branch.gamma
            beta = branch.beta
            eps = branch.eps
        std = ops.sqrt(moving_variance + eps)
        t = ops.reshape(gamma / std, (-1, 1, 1, 1))
        return kernel * t, beta - moving_mean * gamma / std

    def switch_to_deploy(self):
        if self.rbr_reparam is not None:
            return
        kernel, bias = self.get_equivalent_kernel_bias()
        self.rbr_reparam = nn.Conv2d(in_channels=self.rbr_dense.conv.in_channels,
                                     out_channels=self.rbr_dense.conv.out_channels,
                                     kernel_size=self.rbr_dense.conv.kernel_size, stride=self.rbr_dense.conv.stride,
                                     padding=self.rbr_dense.conv.padding, dilation=self.rbr_dense.conv.dilation,
                                     group=self.rbr_dense.conv.group, has_bias=True, pad_mode="pad")
        self.rbr_reparam.weight.data = kernel
        self.rbr_reparam.bias.data = bias
        for para in self.parameters():
            para.detach_()
        self.__delattr__('rbr_dense')
        self.__delattr__('rbr_1x1')
        if hasattr(self, 'rbr_identity'):
            self.__delattr__('rbr_identity')
        if hasattr(self, 'id_tensor'):
            self.__delattr__('id_tensor')
        self.deploy = True


class RepVGG(nn.Cell):
    r"""RepVGG model class, based on
    `"RepVGGBlock: An all-MLP Architecture for Vision" <https://arxiv.org/pdf/2101.03697>`_

    Args:
        num_blocks (list) : number of RepVGGBlocks
        num_classes (int) : number of classification classes. Default: 1000.
        in_channels (in_channels) : number the channels of the input. Default: 3.
        width_multiplier (list) : the numbers of MLP Architecture.
        override_group_map (dict) : the numbers of MLP Architecture.
        deploy (bool) : use rbr_reparam block or not. Default: False
        use_se (bool) : use se_block or not. Default: False
    """

    def __init__(self, num_blocks, num_classes=1000, in_channels=3, width_multiplier=None, override_group_map=None,
                 deploy=False, use_se=False):
        super(RepVGG, self).__init__()

        assert len(width_multiplier) == 4

        self.deploy = deploy
        self.override_group_map = override_group_map or dict()
        self.use_se = use_se

        assert 0 not in self.override_group_map

        self.in_planes = min(64, int(64 * width_multiplier[0]))

        self.stage0 = RepVGGBlock(in_channels=in_channels, out_channels=self.in_planes, kernel_size=3, stride=2,
                                  padding=1,
                                  deploy=self.deploy, use_se=self.use_se)
        self.cur_layer_idx = 1
        self.stage1 = self._make_stage(
            int(64 * width_multiplier[0]), num_blocks[0], stride=2)
        self.stage2 = self._make_stage(
            int(128 * width_multiplier[1]), num_blocks[1], stride=2)
        self.stage3 = self._make_stage(
            int(256 * width_multiplier[2]), num_blocks[2], stride=2)
        self.stage4 = self._make_stage(
            int(512 * width_multiplier[3]), num_blocks[3], stride=2)
        self.gap = GlobalAvgPooling()
        self.linear = nn.Dense(int(512 * width_multiplier[3]), num_classes)
        self._initialize_weights()

    def _make_stage(self, planes, num_blocks, stride):
        strides = [stride] + [1] * (num_blocks - 1)
        blocks = []
        for s in strides:
            cur_group = self.override_group_map.get(self.cur_layer_idx, 1)
            blocks.append(RepVGGBlock(in_channels=self.in_planes, out_channels=planes, kernel_size=3,
                                      stride=s, padding=1, group=cur_group, deploy=self.deploy,
                                      use_se=self.use_se))
            self.in_planes = planes
            self.cur_layer_idx += 1
        return nn.SequentialCell(blocks)

    def _initialize_weights(self):
        for _, cell in self.cells_and_names():
            if isinstance(cell, (nn.Dense, nn.Conv2d)):
                cell.weight.set_data(init.initializer(init.TruncatedNormal(sigma=0.02),
                                                      cell.weight.shape,
                                                      cell.weight.dtype))
                if isinstance(cell, nn.Dense) and cell.bias is not None:
                    cell.bias.set_data(init.initializer(init.Zero(),
                                                        cell.bias.shape,
                                                        cell.bias.dtype))

    def construct(self, x):
        x = self.stage0(x)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        x = self.gap(x)
        x = self.linear(x)
        return x


@register_model
def RepVGG_A0(pretrained: bool = False, num_classes: int = 1000, in_channels=3, **kwargs) -> RepVGG:
    """Get RepVGG model with num_blocks=[2, 4, 14, 1], width_multiplier=[0.75, 0.75, 0.75, 2.5].
     Refer to the base class `models.RepVGG` for more details.
     """
    default_cfg = default_cfgs['RepVGG-A0']
    model = RepVGG(num_blocks=[2, 4, 14, 1], num_classes=num_classes, in_channels=in_channels,
                   width_multiplier=[0.75, 0.75, 0.75, 2.5], override_group_map=None, deploy=False, **kwargs)
    if pretrained:
        load_pretrained(model, default_cfg,
                        num_classes=num_classes, in_channels=in_channels)

    return model


def repvgg_model_convert(model: nn.Cell, save_path=None, do_copy=True):
    """repvgg_model_convert"""
    if do_copy:
        model = copy.deepcopy(model)
    for module in model.modules():
        if hasattr(module, 'switch_to_deploy'):
            module.switch_to_deploy()
    if save_path is not None:
        save_checkpoint(model.parameters_and_names(), save_path)
    return model
