import warnings

import mindspore as ms
import mindspore.dataset.vision as vision
import mindspore.dataset.transforms as transforms

from .transforms_factory import create_transforms


def create_loader(
        dataset,
        batch_size,
        drop_remainder=False,
        is_training=False,
        mixup=0.0,
        num_classes=1000,
        transform=None,
        target_transform=None,
        num_parallel_workers=None,
        python_multiprocessing=False,
):
    r"""Creates dataloader.

    Applies operations such as transform and batch to the `ms.dataset.Dataset` object
    created by the `create_dataset` function to get the dataloader.

    Args:
        dataset (ms.dataset.Dataset): dataset object created by `create_dataset`.
        batch_size (int or function): The number of rows each batch is created with. An
            int or callable object which takes exactly 1 parameter, BatchInfo.
        drop_remainder (bool, optional): Determines whether to drop the last block
            whose data row number is less than batch size (default=False). If True, and if there are less
            than batch_size rows available to make the last batch, then those rows will
            be dropped and not propagated to the child node.
        is_training (bool): whether it is in train mode. Default: False.
        mixup (float): mixup hyperparameter of beta distribution. The value must be positive (default=0.0).
        num_classes (int): the number of classes. Default: 1000.
        transform (list or None): the list of transformations that wil be applied on the image,
            which is obtained by `create_transform`. If None, the default imagenet transformation
            for evaluation will be applied. Default: None.
        target_transform (list or None): the list of transformations that will be applied on the label.
            If None, the label will be converted to the type of ms.int32. Default: None.
        num_parallel_workers (int, optional): Number of workers(threads) to process the dataset in parallel
            (default=None).
        python_multiprocessing (bool, optional): Parallelize Python operations with multiple worker processes. This
            option could be beneficial if the Python operation is computational heavy (default=False).

    Note:
        Args: `is_training`, `mixup`, `num_classes` is used for MixUp, which is a kind of transform operation.
        However, we are not able to merge it into `transform`, due to the limitations of the `mindspore.dataset` API.

    Returns:
        BatchDataset, dataset batched.
    """

    if transform is None:
        warnings.warn("Using None as the default value of transform will set it back to "
                      "traditional image transform, which is not recommended. "
                      "You should explicitly call `create_transforms` and pass it to `create_loader`.")
        transform = create_transforms("imagenet", is_training=False)
    dataset = dataset.map(operations=transform,
                          input_columns='image',
                          num_parallel_workers=num_parallel_workers,
                          python_multiprocessing=python_multiprocessing)
    if target_transform is None:
        target_transform = transforms.TypeCast(ms.int32)
    target_input_columns = 'label' if 'label' in dataset.get_col_names() else 'fine_label'
    dataset = dataset.map(operations=target_transform,
                          input_columns=target_input_columns,
                          num_parallel_workers=num_parallel_workers,
                          python_multiprocessing=python_multiprocessing)

    if is_training and mixup > 0:
        one_hot_encode = transforms.OneHot(num_classes)
        dataset = dataset.map(operations=one_hot_encode, input_columns=[target_input_columns])

    dataset = dataset.batch(batch_size=batch_size, drop_remainder=drop_remainder)

    if is_training and mixup > 0:
        trans_mixup = vision.MixUpBatch(alpha=mixup)
        dataset = dataset.map(input_columns=["image", target_input_columns], num_parallel_workers=num_parallel_workers,
                              operations=trans_mixup)

    return dataset
