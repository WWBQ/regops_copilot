"""文档业务层：上传 PDF → ObjectStore + Registry。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.documents.registry import DocumentRecord, DocumentRegistry
from app.ingest.models import PageBlock
from app.ingest.parse_store import ParseArtifactStore
from app.storage.exceptions import ObjectNotFoundError
from app.storage.local import LocalObjectStore

_DOC_ID_RE = re.compile(r"^[\w.-]+$")


@dataclass(frozen=True)
class UploadResult:
    doc_id: str
    bucket: str
    object_key: str
    content_hash: str
    source_filename: str
    size: int
    reused: bool


class DocumentService:
    def __init__(
        self,
        store: LocalObjectStore,
        registry: DocumentRegistry,
        *,
        default_bucket: str,
        parse_store: ParseArtifactStore | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.default_bucket = default_bucket
        self.parse_store = parse_store or ParseArtifactStore(store, default_bucket=default_bucket)

    @staticmethod
    def content_hash(body: bytes) -> str:
        digest = hashlib.sha256(body).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def infer_doc_id(filename: str) -> str:
        stem = Path(filename).stem
        if _DOC_ID_RE.match(stem):
            return stem
        safe = re.sub(r"[^\w.-]+", "_", stem).strip("_")
        return safe or "document"

    @staticmethod
    def validate_doc_id(doc_id: str) -> str:
        doc_id = doc_id.strip()
        if not doc_id or not _DOC_ID_RE.match(doc_id):
            raise ValueError("doc_id 只允许字母、数字、下划线、点、连字符")
        return doc_id

    def object_key_for(self, doc_id: str, content_hash: str) -> str:
        return f"reports/{doc_id}/{content_hash}.pdf"

    def session_object_key_for(self, session_id: str, content_hash: str) -> str:
        return f"temp/sessions/{session_id}/{content_hash}.pdf"

    @staticmethod
    def make_session_doc_id(session_id: str, content_hash: str) -> str:
        sid = session_id.replace("-", "")[:16]
        digest = content_hash.replace("sha256:", "")[:8]
        return f"sess_{sid}_{digest}"

    def upload_session_pdf(
        self,
        body: bytes,
        source_filename: str,
        *,
        session_id: str,
        content_type: str = "application/pdf",
    ) -> UploadResult:
        """会话级 PDF：temp 路径 + sess_ 前缀 doc_id，不进公司年报主库。"""
        if not body:
            raise ValueError("empty file")
        if not source_filename.lower().endswith(".pdf"):
            raise ValueError("only PDF files are supported")

        digest = self.content_hash(body)
        doc_id = self.make_session_doc_id(session_id, digest)
        object_key = self.session_object_key_for(session_id, digest)
        bucket = self.default_bucket

        existing = self.registry.get(doc_id)
        reused = False
        if existing and existing.content_hash == digest and self.store.object_exists(bucket, object_key):
            reused = True
        else:
            self.store.put_object(bucket, object_key, body, content_type=content_type)
            self.registry.upsert(
                DocumentRecord(
                    doc_id=doc_id,
                    bucket=bucket,
                    object_key=object_key,
                    content_hash=digest,
                    source_filename=source_filename,
                    content_type=content_type,
                    size=len(body),
                    created_at="",
                    updated_at="",
                )
            )

        return UploadResult(
            doc_id=doc_id,
            bucket=bucket,
            object_key=object_key,
            content_hash=digest,
            source_filename=source_filename,
            size=len(body),
            reused=reused,
        )

    def upload_pdf(
        self,
        body: bytes,
        source_filename: str,
        *,
        doc_id: str | None = None,
        content_type: str = "application/pdf",
    ) -> UploadResult:
        if not body:
            raise ValueError("empty file")
        if not source_filename.lower().endswith(".pdf"):
            raise ValueError("only PDF files are supported")

        resolved_doc_id = self.validate_doc_id(doc_id or self.infer_doc_id(source_filename))
        digest = self.content_hash(body)
        object_key = self.object_key_for(resolved_doc_id, digest)
        bucket = self.default_bucket

        existing = self.registry.get(resolved_doc_id)
        reused = False
        if existing and existing.content_hash == digest and self.store.object_exists(bucket, object_key):
            reused = True
        else:
            self.store.put_object(bucket, object_key, body, content_type=content_type)
            self.registry.upsert(
                DocumentRecord(
                    doc_id=resolved_doc_id,
                    bucket=bucket,
                    object_key=object_key,
                    content_hash=digest,
                    source_filename=source_filename,
                    content_type=content_type,
                    size=len(body),
                    created_at="",
                    updated_at="",
                )
            )

        return UploadResult(
            doc_id=resolved_doc_id,
            bucket=bucket,
            object_key=object_key,
            content_hash=digest,
            source_filename=source_filename,
            size=len(body),
            reused=reused,
        )

    def get_record(self, doc_id: str) -> DocumentRecord:
        record = self.registry.get(doc_id)
        if record is None:
            raise ObjectNotFoundError(f"document not found: {doc_id}")
        return record

    def viewer_url(self, doc_id: str, *, page: int | None = None, expires_in: int = 300) -> str:
        record = self.get_record(doc_id)
        return self.store.generate_presigned_url(
            record.bucket,
            record.object_key,
            expires_in=expires_in,
            page=page,
        )

    def local_pdf_path(self, doc_id: str) -> Path:
        record = self.get_record(doc_id)
        return self.store.resolve_local_path(record.bucket, record.object_key)

    def save_parse_artifact(self, doc_id: str, blocks: list[PageBlock]) -> str:
        """整份解析 JSON 写入 ObjectStore，并更新 registry 中的 parse_object_key。"""
        record = self.get_record(doc_id)
        if blocks and blocks[0].content_hash != record.content_hash:
            raise ValueError("parse result content_hash does not match uploaded PDF")
        parse_object_key, _ = self.parse_store.save_blocks(doc_id, blocks, source_type="pdf")
        self.registry.upsert(
            DocumentRecord(
                doc_id=record.doc_id,
                bucket=record.bucket,
                object_key=record.object_key,
                content_hash=record.content_hash,
                source_filename=record.source_filename,
                content_type=record.content_type,
                size=record.size,
                parse_object_key=parse_object_key,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
        )
        return parse_object_key

    def load_parse_artifact(self, doc_id: str) -> list[PageBlock]:
        record = self.get_record(doc_id)
        if record.parse_object_key:
            body = self.store.get_object(record.bucket, record.parse_object_key)
            from app.ingest.artifact import blocks_from_json_bytes

            return blocks_from_json_bytes(body)
        return self.parse_store.load_blocks(doc_id, record.content_hash, source_type="pdf")

    def parse_artifact_viewer_url(self, doc_id: str, *, expires_in: int = 300) -> str:
        record = self.get_record(doc_id)
        key = record.parse_object_key or self.parse_store.object_key_for(
            record.doc_id, record.content_hash, source_type="pdf"
        )
        if not self.store.object_exists(record.bucket, key):
            raise ObjectNotFoundError(f"parse artifact not found: {doc_id}")
        return self.store.generate_presigned_url(record.bucket, key, expires_in=expires_in)
