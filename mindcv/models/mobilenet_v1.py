"""
MindSpore implementation of `MobileNetV1`.
Refer to MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications.
"""

import math

import mindspore.nn as nn
import mindspore.common.initializer as init
from mindspore import Tensor

from .utils import load_pretrained
from .registry import register_model
from .layers.pooling import GlobalAvgPooling

__all__ = [
    'MobileNetV1',
    'mobilenet_v1_025_224',
    'mobilenet_v1_050_224',
    'mobilenet_v1_075_224',
    'mobilenet_v1_100_224',
]


def _cfg(url='', **kwargs):
    return {
        'url': url,
        'num_classes': 1000,
        'first_conv': '', 'classifier': '',
        **kwargs
    }


default_cfgs = {
    'mobilenet_v1_0.25_224': _cfg(url=''),
    'mobilenet_v1_0.5_224': _cfg(url=''),
    'mobilenet_v1_0.75_224': _cfg(url=''),
    'mobilenet_v1_1.0_224': _cfg(url=''),

}


def depthwise_separable_conv(inp: int, oup: int, stride: int) -> nn.SequentialCell:
    return nn.SequentialCell(
        # dw
        nn.Conv2d(inp, inp, 3, stride, pad_mode="pad", padding=1, group=inp, has_bias=False),
        nn.BatchNorm2d(inp),
        nn.ReLU(),
        # pw
        nn.Conv2d(inp, oup, 1, 1, pad_mode="pad", padding=0, has_bias=False),
        nn.BatchNorm2d(oup),
        nn.ReLU(),
    )


class MobileNetV1(nn.Cell):
    r"""MobileNetV1 model class, based on
    `"MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications" <https://arxiv.org/abs/1704.04861>`_

    Args:
        alpha: scale factor of model width. Default: 1.
        in_channels: number the channels of the input. Default: 3.
        num_classes: number of classification classes. Default: 1000.
    """

    def __init__(self,
                 alpha: float = 1.,
                 in_channels: int = 3,
                 num_classes: int = 1000) -> None:
        super(MobileNetV1, self).__init__()
        input_channels = int(32 * alpha)
        # Setting of depth-wise separable conv
        # c: number of output channel
        # s: stride of depth-wise conv
        block_setting = [
            # c, s
            [64, 1],
            [128, 2],
            [128, 1],
            [256, 2],
            [256, 1],
            [512, 2],
            [512, 1],
            [512, 1],
            [512, 1],
            [512, 1],
            [512, 1],
            [1024, 2],
            [1024, 1],
        ]

        features = [
            nn.Conv2d(in_channels, input_channels, 3, 2, pad_mode="pad", padding=1, has_bias=False),
            nn.BatchNorm2d(input_channels),
            nn.ReLU()
        ]
        for c, s in block_setting:
            output_channel = int(c * alpha)
            features.append(depthwise_separable_conv(input_channels, output_channel, s))
            input_channels = output_channel
        self.features = nn.SequentialCell(features)

        self.pool = GlobalAvgPooling()
        self.classifier = nn.Dense(input_channels, num_classes)
        self._initialize_weights()

    def _initialize_weights(self) -> None:
        for _, cell in self.cells_and_names():
            if isinstance(cell, nn.Conv2d):
                n = cell.kernel_size[0] * cell.kernel_size[1] * cell.out_channels
                cell.weight.set_data(
                    init.initializer(init.Normal(sigma=math.sqrt(2. / n), mean=0.0),
                                     cell.weight.shape, cell.weight.dtype))
                if cell.bias is not None:
                    cell.bias.set_data(init.initializer('zeros', cell.bias.shape, cell.bias.dtype))
            elif isinstance(cell, nn.BatchNorm2d):
                cell.gamma.set_data(init.initializer('ones', cell.gamma.shape, cell.gamma.dtype))
                cell.beta.set_data(init.initializer('zeros', cell.beta.shape, cell.beta.dtype))
            elif isinstance(cell, nn.Dense):
                cell.weight.set_data(
                    init.initializer(init.Normal(sigma=0.01, mean=0.0), cell.weight.shape, cell.weight.dtype))
                if cell.bias is not None:
                    cell.bias.set_data(init.initializer('zeros', cell.bias.shape, cell.bias.dtype))

    def forward_features(self, x: Tensor) -> Tensor:
        x = self.features(x)
        return x

    def forward_head(self, x: Tensor) -> Tensor:
        x = self.pool(x)
        x = self.classifier(x)
        return x

    def construct(self, x: Tensor) -> Tensor:
        x = self.forward_features(x)
        x = self.forward_head(x)
        return x


@register_model
def mobilenet_v1_025_224(pretrained: bool = False, num_classes: int = 1000, in_channels=3, **kwargs) -> MobileNetV1:
    """Get MobileNetV1 model with width scaled by 0.25.
     Refer to the base class `models.MobileNetV1` for more details.
     """
    default_cfg = default_cfgs['mobilenet_v1_0.25_224']
    model = MobileNetV1(alpha=0.25, in_channels=in_channels, num_classes=num_classes, **kwargs)

    if pretrained:
        load_pretrained(model, default_cfg, num_classes=num_classes, in_channels=in_channels)

    return model


@register_model
def mobilenet_v1_050_224(pretrained: bool = False, num_classes: int = 1000, in_channels=3, **kwargs) -> MobileNetV1:
    """Get MobileNetV1 model with width scaled by 0.5.
     Refer to the base class `models.MobileNetV1` for more details.
     """
    default_cfg = default_cfgs['mobilenet_v1_0.5_224']
    model = MobileNetV1(alpha=0.5, in_channels=in_channels, num_classes=num_classes, **kwargs)

    if pretrained:
        load_pretrained(model, default_cfg, num_classes=num_classes, in_channels=in_channels)

    return model


@register_model
def mobilenet_v1_075_224(pretrained: bool = False, num_classes: int = 1000, in_channels=3, **kwargs) -> MobileNetV1:
    """Get MobileNetV1 model with width scaled by 0.75.
     Refer to the base class `models.MobileNetV1` for more details.
     """
    default_cfg = default_cfgs['mobilenet_v1_0.75_224']
    model = MobileNetV1(alpha=0.75, in_channels=in_channels, num_classes=num_classes, **kwargs)

    if pretrained:
        load_pretrained(model, default_cfg, num_classes=num_classes, in_channels=in_channels)

    return model


@register_model
def mobilenet_v1_100_224(pretrained: bool = False, num_classes: int = 1000, in_channels=3, **kwargs) -> MobileNetV1:
    """Get MobileNetV1 model without width scaling.
     Refer to the base class `models.MobileNetV1` for more details.
     """
    default_cfg = default_cfgs['mobilenet_v1_1.0_224']
    model = MobileNetV1(alpha=1.0, in_channels=in_channels, num_classes=num_classes, **kwargs)

    if pretrained:
        load_pretrained(model, default_cfg, num_classes=num_classes, in_channels=in_channels)

    return model
