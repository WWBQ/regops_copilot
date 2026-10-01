"""本地磁盘 ObjectStore：目录布局模拟 COS bucket/key。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.storage.exceptions import ObjectNotFoundError, ObjectStoreError
from app.storage.presign import build_presigned_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObjectMeta:
    bucket: str
    key: str
    size: int
    content_type: str
    etag: str
    last_modified: datetime


class LocalObjectStore:
    """COS 的本地等价物：data/objects/{bucket}/{key}。"""

    def __init__(
        self,
        root: Path,
        *,
        default_bucket: str,
        public_base_url: str,
        presign_secret: str,
    ) -> None:
        self.root = root
        self.default_bucket = default_bucket
        self.public_base_url = public_base_url
        self.presign_secret = presign_secret
        self.root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, bucket: str, key: str) -> Path:
        safe_key = key.lstrip("/")
        if not safe_key or ".." in Path(safe_key).parts:
            raise ObjectStoreError(f"invalid object key: {key}")
        return self.root / bucket / safe_key

    def _meta_path(self, bucket: str, key: str) -> Path:
        return self._object_path(bucket, f"{key.lstrip('/')}.meta.json")

    @staticmethod
    def _etag(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def _write_meta(self, bucket: str, key: str, meta: ObjectMeta) -> None:
        path = self._meta_path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "bucket": meta.bucket,
            "key": meta.key,
            "size": meta.size,
            "content_type": meta.content_type,
            "etag": meta.etag,
            "last_modified": meta.last_modified.isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_meta(self, bucket: str, key: str, *, fallback_size: int | None = None) -> ObjectMeta:
        meta_path = self._meta_path(bucket, key)
        obj_path = self._object_path(bucket, key)
        if meta_path.is_file():
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            return ObjectMeta(
                bucket=raw["bucket"],
                key=raw["key"],
                size=int(raw["size"]),
                content_type=raw["content_type"],
                etag=raw["etag"],
                last_modified=datetime.fromisoformat(raw["last_modified"]),
            )
        if not obj_path.is_file():
            raise ObjectNotFoundError(f"object not found: {bucket}/{key}")
        stat = obj_path.stat()
        return ObjectMeta(
            bucket=bucket,
            key=key,
            size=fallback_size if fallback_size is not None else stat.st_size,
            content_type="application/octet-stream",
            etag=self._etag(obj_path.read_bytes()),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> ObjectMeta:
        obj_path = self._object_path(bucket, key)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = obj_path.with_suffix(obj_path.suffix + ".part")
        tmp_path.write_bytes(body)
        tmp_path.replace(obj_path)
        meta = ObjectMeta(
            bucket=bucket,
            key=key,
            size=len(body),
            content_type=content_type,
            etag=self._etag(body),
            last_modified=datetime.now(tz=UTC),
        )
        self._write_meta(bucket, key, meta)
        logger.info("put_object bucket=%s key=%s size=%d", bucket, key, len(body))
        return meta

    def get_object(self, bucket: str, key: str) -> bytes:
        obj_path = self._object_path(bucket, key)
        if not obj_path.is_file():
            raise ObjectNotFoundError(f"object not found: {bucket}/{key}")
        return obj_path.read_bytes()

    def head_object(self, bucket: str, key: str) -> ObjectMeta:
        obj_path = self._object_path(bucket, key)
        if not obj_path.is_file():
            raise ObjectNotFoundError(f"object not found: {bucket}/{key}")
        return self._read_meta(bucket, key)

    def object_exists(self, bucket: str, key: str) -> bool:
        return self._object_path(bucket, key).is_file()

    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        *,
        expires_in: int = 300,
        page: int | None = None,
    ) -> str:
        if not self.object_exists(bucket, key):
            raise ObjectNotFoundError(f"object not found: {bucket}/{key}")
        url, _ = build_presigned_url(
            method="GET",
            base_url=self.public_base_url,
            bucket=bucket,
            key=key,
            secret=self.presign_secret,
            expires_in=expires_in,
        )
        if page is not None and page > 0:
            url = f"{url}#page={page}"
        return url

    def resolve_local_path(self, bucket: str, key: str) -> Path:
        obj_path = self._object_path(bucket, key)
        if not obj_path.is_file():
            raise ObjectNotFoundError(f"object not found: {bucket}/{key}")
        return obj_path.resolve()
