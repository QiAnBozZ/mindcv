# Copyright 2020-2022 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""adan"""
from __future__ import absolute_import

import numpy as np

from mindspore import context
from mindspore.common import dtype as mstype
from mindspore.common.initializer import initializer
from mindspore.common.api import ms_function
from mindspore.ops import operations as P
from mindspore.ops import composite as C
from mindspore.ops import functional as F
from mindspore.common.parameter import Parameter
from mindspore.common.tensor import Tensor
from mindspore._checkparam import Validator as validator
from mindspore._checkparam import Rel
from mindspore.nn.optim.optimizer import Optimizer
from mindspore.nn.optim.optimizer import opt_init_args_register
from mindspore.nn.optim._dist_optimizer_registry import _register_dist_optimizer

_adan_opt = C.MultitypeFuncGraph("adan_opt")
#_fused_adan_weight_decay = C.MultitypeFuncGraph("fused_adan_weight_decay")
_scaler_one = Tensor(1, mstype.int32)
_scaler_ten = Tensor(10, mstype.float32)


'''
@_adan_opt.register("Function", "Function", "Function", "Function",
                    "Bool", "Bool", "Bool", "Bool",
                    "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor",
                    "RowTensor", "Tensor", "Tensor", "Tensor", "Tensor", "Bool", "Bool", "RowTensor")
def _run_opt_with_sparse(opt, sparse_opt, push, pull,
                         use_locking, use_nesterov, use_amsgrad, target,
                         beta1_power, beta2_power, beta1, beta2, eps, lr,
                         gradient, param, m, v, vhat, ps_parameter, cache_enable, prev_gradient):

    success = True
    indices = gradient.indices
    values = gradient.values
    if ps_parameter and not cache_enable:
        op_shape = P.Shape()
        shapes = (op_shape(param), op_shape(m), op_shape(v),
                  op_shape(beta1_power), op_shape(beta2_power), op_shape(lr), op_shape(beta1),
                  op_shape(beta2), op_shape(eps), op_shape(values), op_shape(indices))
        success = F.depend(success, pull(push((beta1_power, beta2_power, lr, beta1, beta2,
                                               eps, values, indices), shapes), param))
        return success

    if not target:
        success = F.depend(success, sparse_opt(param, m, v, beta1_power, beta2_power, lr, beta1, beta2,
                                               eps, values, indices))
    else:
        op_mul = P.Mul()
        op_square = P.Square()
        op_sqrt = P.Sqrt()
        scatter_add = P.ScatterAdd(use_locking)

        success = F.depend(success, F.assign(m, op_mul(F.tuple_to_array((1.0,)) - beta1, m)))
        success = F.depend(success, F.assign(v, op_mul(F.tuple_to_array((1.0,)) - beta2, v)))
        success = F.depend(success, F.assign(n, op_mul(F.tuple_to_array((1.0,)) - beta3, n)))

        grad_indices = gradient.indices
        grad_value = gradient.values
        prev_grad_value = prev_gradient.values

        next_m = scatter_add(m,
                             grad_indices,
                             op_mul(beta1, grad_value))

        next_v = scatter_add(v,
                             grad_indices,
                             op_mul(beta2, grad_value - prev_grad_value))

        next_n = scatter_add(n,
                             grad_indices,
                             op_mul(beta3, op_square(
                                 grad_value + op_mul(F.tuple_to_array((1.0,)) - beta2, grad_value - prev_grad_value))))

        lr_t = lr / ( op_sqrt(next_n) + eps)



        next_param = param - lr_t * param_update

        success = F.depend(success, F.assign(param, next_param))
        success = F.depend(success, F.assign(m, next_m))
        success = F.depend(success, F.assign(v, next_v))
        success = F.depend(success, F.assign(prev_gradient, gradient))

    return success
'''



@_adan_opt.register("Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor", "Tensor")
def _update_run_op(beta1, beta2, beta3, eps, lr, weight_decay, param, m, v, n, gradient, prev_gradient):
    """
    Update parameters.

    Args:
        beta1 (Tensor): The exponential decay rate for the 1st moment estimations. Should be in range (0.0, 1.0).
        beta2 (Tensor): The exponential decay rate for the 2nd moment estimations. Should be in range (0.0, 1.0).
        eps (Tensor): Term added to the denominator to improve numerical stability. Should be greater than 0.
        lr (Tensor): Learning rate.
        weight_decay (numbers.Number): Weight decay. Should be equal to or greater than 0. if 0, no decay
        param (Tensor): Parameters.
        m (Tensor): m value of parameters.
        v (Tensor): v value of parameters.
        gradient (Tensor): Gradient of parameters.

    Returns:
        Tensor, the new value of v after updating.
    """
    op_cast = P.Cast()
    op_mul = P.Mul()
    op_square = P.Square()
    op_sqrt = P.Sqrt()
    op_cast = P.Cast()
    op_reshape = P.Reshape()
    op_shape = P.Shape()

    success = True

    #if global_step == 0.0: # init 
    # TODO: use global_step==0 as the condition to init prev_gradient as gradient 
    #if (F.reduce_min(prev_gradient) == 0.0) and (F.reduce_max(prev_gradient) == 0.0):
    if (F.reduce_sum(prev_gradient) == 0.0):
        success = F.depend(success, F.assign(prev_gradient, gradient))


    # TODO: is casting needed? 
    param_fp32 = op_cast(param, mstype.float32)
    m_fp32 = op_cast(m, mstype.float32)
    v_fp32 = op_cast(v, mstype.float32)
    n_fp32 = op_cast(n, mstype.float32)
    gradient_fp32 = op_cast(gradient, mstype.float32)
    prev_gradient_fp32 = op_cast(prev_gradient, mstype.float32)

    next_m = op_mul(F.tuple_to_array((1.0,)) - beta1, m_fp32) + op_mul(beta1, gradient_fp32)

    next_v = op_mul(F.tuple_to_array((1.0,)) - beta2, v_fp32) + op_mul(beta2, gradient_fp32 - prev_gradient_fp32)

    next_n = op_mul(F.tuple_to_array((1.0,)) - beta3, n_fp32) + op_mul(beta3, 
                    op_square(
                        gradient + op_mul(F.tuple_to_array((1.0,)) - beta2, gradient_fp32 - prev_gradient_fp32)
                        )
                    )

    lr_t = lr /  (eps + op_sqrt(next_n))


    update = next_m + op_mul(F.tuple_to_array((1.0,)) - beta2, next_v)  

    #if decay_flag:
    #    update = op_mul(weight_decay, param_fp32) + update

    next_param = param_fp32 - op_reshape(op_mul(lr, update), op_shape(param_fp32))

    next_param = next_param / (Tensor(1.0, mstype.float32)  + op_mul(weight_decay, lr))

    success= F.depend(success, F.assign(param, op_cast(next_param, F.dtype(param))))
    success= F.depend(success, F.assign(m, op_cast(next_m, F.dtype(m))))
    success= F.depend(success, F.assign(v, op_cast(next_v, F.dtype(v))))
    success= F.depend(success, F.assign(n, op_cast(next_n, F.dtype(n))))
    success = F.depend(success, F.assign(prev_gradient, gradient))

    return op_cast(next_param, F.dtype(param))


def _check_param_value(beta1, beta2, eps, prim_name):
    """Check the type of inputs."""
    validator.check_value_type("beta1", beta1, [float], prim_name)
    validator.check_value_type("beta2", beta2, [float], prim_name)
    validator.check_value_type("eps", eps, [float], prim_name)
    validator.check_float_range(beta1, 0.0, 1.0, Rel.INC_NEITHER, "beta1", prim_name)
    validator.check_float_range(beta2, 0.0, 1.0, Rel.INC_NEITHER, "beta2", prim_name)
    validator.check_positive_float(eps, "eps", prim_name)


class Adan(Optimizer):
    '''
    The Adan (ADAptive Nesterov momentum algorithm) Optimizer from https://arxiv.org/abs/2208.06677  

    Note: it is an experimental version. 
    '''
    @opt_init_args_register
    def __init__(self, params, learning_rate=1e-3, beta1=0.98, beta2=0.92, beta3=0.99, eps=1e-8, use_locking=False,
                 weight_decay=1e-6, loss_scale=1.0):
        super(Adan, self).__init__(learning_rate, params, weight_decay=weight_decay, loss_scale=loss_scale) # Optimized inherit weight decay is bloaked. weight decay is computed in this py. 

        _check_param_value(beta1, beta2, eps, self.cls_name)
        validator.check_value_type("use_locking", use_locking, [bool], self.cls_name)

        self.beta1 = Tensor(beta1, mstype.float32)
        self.beta2 = Tensor(beta2, mstype.float32)
        self.beta3 = Tensor(beta3, mstype.float32)
        #self.beta1_power = Parameter(initializer(1, [1], mstype.float32), name="beta1_power")
        #self.beta2_power = Parameter(initializer(1, [1], mstype.float32), name="beta2_power")
        #self.beta3_power = Parameter(initializer(1, [1], mstype.float32), name="beta3_power")
        self.eps = Tensor(eps, mstype.float32)
        self.use_locking = use_locking
        self.moment1 = self._parameters.clone(prefix="moment1", init='zeros') # m 
        self.moment2 = self._parameters.clone(prefix="moment2", init='zeros') # v
        self.moment3 = self._parameters.clone(prefix="moment3", init='zeros') # n
        self.prev_gradient= self._parameters.clone(prefix="prev_gradient", init='zeros') 
        # print('prev g: ', type(self.prev_gradient))
       
        self.weight_decay = Tensor(weight_decay, mstype.float32)

        #self.vhat = self._parameters.clone(prefix="vhat", init='zeros')

        #self._is_device = True
        
        # TODO: 
        #self.opt = P.Adam(use_locking, use_nesterov)

        #self.sparse_opt = P.FusedSparseAdam(use_locking, use_nesterov)
        #self.sparse_opt.add_prim_attr("primitive_target", "CPU")
        #self._ps_pull = P.Pull()

        #self._ps_push = P.Push("Adan", [0, 1, 2])
        #self._ps_push.add_prim_attr("use_nesterov", use_nesterov)

        #self._init_distributed_opts(use_locking, use_nesterov)

    @ms_function
    def construct(self, gradients):
        params = self._parameters
        moment1 = self.moment1
        moment2 = self.moment2
        moment3 = self.moment3
        #vhat = self.vhat
        gradients = self.flatten_gradients(gradients)
        #gradients = self.decay_weight(gradients) # we decay weight in adan_opt func 
        gradients = self.gradients_centralization(gradients)
        gradients = self.scale_grad(gradients)
        gradients = self._grad_sparse_indices_deduplicate(gradients)
        lr = self.get_lr()
        #weight_decay = self.get_weight_decay()

        #if self.global_step == 0:
        #    success = F.depend(True, F.assign(self.prev_gradient, gradients))

        #TODO: currently not support dist 
        success = self.map_(F.partial(_adan_opt, self.beta1, self.beta2, self.beta3, self.eps, lr, self.weight_decay),
                params, moment1, moment2, moment3, gradients, self.prev_gradient)
                #params, moment1, moment2, moment3, gradients, self.prev_gradient, self.global_step)


        return success

    @Optimizer.target.setter
    def target(self, value):
        """
        If the input value is set to "CPU", the parameters will be updated on the host using the Fused
        optimizer operation.
        """
        self._set_base_target(value)
    '''
    def _init_distributed_opts(self, use_locking, use_nesterov):
        self.use_dist_optimizer = self._use_distibuted_optimizer()
        self.dense_adan_opts, self.use_dense_opt_flags = \
            self._get_distributed_optimizer_list("adan", use_locking, use_nesterov)
        self.sparse_adan_opts, self.use_sparse_opt_flags = \
            self._get_distributed_optimizer_list("fused_sparse_adan", use_locking, use_nesterov)
    '''

'''
def create_distributed_adan(*args, **kwargs):
    """
    Create the distributed Adan op.
    """
    adan = P.Adan(*args, **kwargs)
    adan.add_prim_attr("gradient_type", "dense_gradient")
    adan.add_prim_attr("parameter_input_index", 0)
    adan.add_prim_attr("gradient_input_index", 9)
    return adan


def create_distributed_fused_sparse_adan(*args, **kwargs):
    """
    Create the distributed FusedSparseAdan op.
    """
    sparse_adan = P.FusedSparseAdan(*args, **kwargs)
    sparse_adan.add_prim_attr("gradient_type", "sparse_gradient")
    sparse_adan.add_prim_attr("parameter_input_index", 0)
    sparse_adan.add_prim_attr("gradient_input_index", 9)
    sparse_adan.add_prim_attr("indices_input_index", 10)
    return sparse_adan


_register_dist_optimizer("adan", create_distributed_adan)
_register_dist_optimizer("fused_sparse_adan", create_distributed_fused_sparse_adan)

'''
