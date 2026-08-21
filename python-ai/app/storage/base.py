"""ObjectStore 协议：与 COS PutObject / GetObject / HeadObject 对齐。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ObjectMeta:
    bucket: str
    key: str
    size: int
    content_type: str
    etag: str
    last_modified: datetime


class ObjectStore(Protocol):
    def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ObjectMeta:
        """上传对象，幂等覆盖同 key。"""

    def get_object(self, bucket: str, key: str) -> bytes:
        """读取对象全文。"""

    def head_object(self, bucket: str, key: str) -> ObjectMeta:
        """读取对象元数据，不下载正文。"""

    def object_exists(self, bucket: str, key: str) -> bool:
        """对象是否存在。"""

    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        *,
        expires_in: int = 300,
        page: int | None = None,
    ) -> str:
        """生成短期可读 URL；可选 #page 供 PDF 查看器跳页。"""

    def resolve_local_path(self, bucket: str, key: str) -> Path:
        """本地实现返回磁盘路径；云实现应下载到临时文件。"""
