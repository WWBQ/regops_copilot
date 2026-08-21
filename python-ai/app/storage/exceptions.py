class ObjectStoreError(Exception):
    """对象存储操作失败。"""


class ObjectNotFoundError(ObjectStoreError):
    """Bucket 或 object key 不存在。"""
