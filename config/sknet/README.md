# SKNet

***

> [SKNet: Selective Kernel Networks](https://arxiv.org/pdf/1903.06586.pdf)

## Introduction

***

The core idea of SKNet: SK Convolution 

1. Split is to perform different receptive field convolution operations. The upper branch is a 3 x 3 kernel with dilate size=1, and the lower one is a 3 x 3 convolution with dilate size=2. 
2. Fuse performs feature fusion, superimposes the convolutional features of the two branches, and then performs the standard SE process (Global AVG, FC-BN-ReLU, FC), where the last FC is the channel weight of the two branches. vector 
3. Select is to perform the respective Softmax operation on the channel weight vector of the last two branches of the Fuse, similar to the gate mechanism, the respective weights of each channel in the two branches can be obtained, multiplied back to the original features, and finally performed. Feature stacking.

## Benchmark

***

|        |         |           |           |    Pynative     |  Pynative  |     Graph      |   Graph    |           |            |
| :----: | ------- | :-------: | :-------: | :-------------: | :--------: | :------------: | :--------: | :-------: | :--------: |
|        | Model   | Top-1 (%) | Top-5 (%) | train (s/epoch) | Infer (ms) | train(s/epoch) | Infer (ms) | Download  |   Config   |
|  GPU   | sknet50 |           |           |                 |            |                |            | [model]() | [config]() |
| Ascend | sknet50 |           |           |                 |            |                |            |           |            |



## Examples

***

### Train

- The [yaml config files](../../config) that yield competitive results on ImageNet  for different models are listed in the `config` folder. To trigger training using preset yaml config. 

  ```shell
  comming soon
  ```


- Here is the example for finetuning a pretrained SKNet on CIFAR10 dataset using Adam optimizer.

  ```shell
  python train.py --model=sknet50 --pretrained --opt=momentum --lr=0.001 dataset=cifar10 --num_classes=10 --dataset_download
  ```

Detailed adjustable parameters and their default value can be seen in [config.py](../../config.py).

### Eval

- To validate the model, you can use `validate.py`. Here is an example to verify the accuracy of pretrained weights.

  ```shell
  python validate.py --model=sknet50 --dataset=imagenet --val_split=val --pretrained
  ```

- To validate the model, you can use `validate.py`. Here is an example to verify the accuracy of your training.

  ```python
  python validate.py --model=sknet50 --dataset=imagenet --val_split=val --ckpt_path='./ckpt/sknet50-best.ckpt'
  ```

