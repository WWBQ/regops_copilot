"""解析 JSON 写入 ObjectStore，供回溯与免重复 Docling。"""

from __future__ import annotations

import logging

from app.ingest.artifact import blocks_from_json_bytes, blocks_to_json_bytes
from app.ingest.models import PageBlock
from app.storage.local import LocalObjectStore

logger = logging.getLogger(__name__)

PARSE_CONTENT_TYPE = "application/json; charset=utf-8"


class ParseArtifactStore:
    def __init__(self, store: LocalObjectStore, *, default_bucket: str) -> None:
        self.store = store
        self.default_bucket = default_bucket

    @staticmethod
    def object_key_for(doc_id: str, content_hash: str, *, source_type: str = "pdf") -> str:
        return f"parsed/{source_type}/{doc_id}/{content_hash}.parse.json"

    def save_blocks(
        self,
        doc_id: str,
        blocks: list[PageBlock],
        *,
        source_type: str = "pdf",
    ) -> tuple[str, str]:
        if not blocks:
            raise ValueError("empty parse result")
        content_hash = blocks[0].content_hash
        object_key = self.object_key_for(doc_id, content_hash, source_type=source_type)
        body = blocks_to_json_bytes(blocks)
        self.store.put_object(
            self.default_bucket,
            object_key,
            body,
            content_type=PARSE_CONTENT_TYPE,
        )
        logger.info(
            "parse artifact saved doc_id=%s key=%s pages=%d bytes=%d",
            doc_id,
            object_key,
            len(blocks),
            len(body),
        )
        return object_key, content_hash

    def load_blocks(
        self,
        doc_id: str,
        content_hash: str,
        *,
        source_type: str = "pdf",
    ) -> list[PageBlock]:
        object_key = self.object_key_for(doc_id, content_hash, source_type=source_type)
        body = self.store.get_object(self.default_bucket, object_key)
        blocks = blocks_from_json_bytes(body)
        if blocks and blocks[0].content_hash != content_hash:
            raise ValueError("parse artifact content_hash mismatch")
        return blocks

    def exists(self, doc_id: str, content_hash: str, *, source_type: str = "pdf") -> bool:
        object_key = self.object_key_for(doc_id, content_hash, source_type=source_type)
        return self.store.object_exists(self.default_bucket, object_key)
