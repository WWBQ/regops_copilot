"""对象存储抽象：本地实现模拟 COS，生产可替换为腾讯云 SDK。"""

from app.storage.base import ObjectMeta, ObjectStore
from app.storage.exceptions import ObjectNotFoundError, ObjectStoreError
from app.storage.local import LocalObjectStore

__all__ = [
    "LocalObjectStore",
    "ObjectMeta",
    "ObjectNotFoundError",
    "ObjectStore",
    "ObjectStoreError",
]
