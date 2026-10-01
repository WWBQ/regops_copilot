"""文档业务层：对象存储保存正文，PostgreSQL 保存唯一元数据。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db.connection import get_connection
from app.db.pdf_document_repository import (
    DocumentRecord,
    get_pdf_document,
    list_pdf_documents,
    update_pdf_document_ingest,
    upsert_uploaded_pdf_document,
)
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
        *,
        default_bucket: str,
        parse_store: ParseArtifactStore | None = None,
    ) -> None:
        self.store = store
        self.default_bucket = default_bucket
        self.parse_store = parse_store or ParseArtifactStore(store, default_bucket=default_bucket)

    @staticmethod
    def content_hash(body: bytes) -> str:
        return f"sha256:{hashlib.sha256(body).hexdigest()}"

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

    @staticmethod
    def object_key_for(doc_id: str, content_hash: str) -> str:
        return f"reports/{doc_id}/{content_hash}.pdf"

    @staticmethod
    def session_object_key_for(session_id: str, content_hash: str) -> str:
        return f"temp/sessions/{session_id}/{content_hash}.pdf"

    @staticmethod
    def make_session_doc_id(session_id: str, content_hash: str) -> str:
        sid = session_id.replace("-", "")[:16]
        digest = content_hash.replace("sha256:", "")[:8]
        return f"sess_{sid}_{digest}"

    def _upload(
        self,
        body: bytes,
        source_filename: str,
        *,
        doc_id: str,
        object_key: str,
        content_type: str,
        doc_type: str,
        meta: dict[str, Any] | None = None,
    ) -> UploadResult:
        digest = self.content_hash(body)
        with get_connection() as conn:
            existing = get_pdf_document(conn, doc_id)
        reused = bool(
            existing
            and existing.content_hash == digest
            and existing.object_key == object_key
            and self.store.object_exists(self.default_bucket, object_key)
        )
        if not reused:
            self.store.put_object(self.default_bucket, object_key, body, content_type=content_type)
        with get_connection() as conn:
            upsert_uploaded_pdf_document(
                conn,
                doc_id=doc_id,
                source_filename=source_filename,
                content_type=content_type,
                content_hash=digest,
                bucket=self.default_bucket,
                object_key=object_key,
                file_size=len(body),
                doc_type=doc_type,
                ingest_status=existing.ingest_status if reused and existing else "uploaded",
                meta=meta,
            )
            conn.commit()
        return UploadResult(
            doc_id=doc_id,
            bucket=self.default_bucket,
            object_key=object_key,
            content_hash=digest,
            source_filename=source_filename,
            size=len(body),
            reused=reused,
        )

    def upload_session_pdf(
        self,
        body: bytes,
        source_filename: str,
        *,
        session_id: str,
        content_type: str = "application/pdf",
    ) -> UploadResult:
        self._validate_pdf(body, source_filename)
        digest = self.content_hash(body)
        doc_id = self.make_session_doc_id(session_id, digest)
        return self._upload(
            body,
            source_filename,
            doc_id=doc_id,
            object_key=self.session_object_key_for(session_id, digest),
            content_type=content_type,
            doc_type="session_upload",
            meta={"scope": "session", "session_id": session_id},
        )

    def upload_pdf(
        self,
        body: bytes,
        source_filename: str,
        *,
        doc_id: str | None = None,
        content_type: str = "application/pdf",
    ) -> UploadResult:
        self._validate_pdf(body, source_filename)
        resolved_doc_id = self.validate_doc_id(doc_id or self.infer_doc_id(source_filename))
        digest = self.content_hash(body)
        return self._upload(
            body,
            source_filename,
            doc_id=resolved_doc_id,
            object_key=self.object_key_for(resolved_doc_id, digest),
            content_type=content_type,
            doc_type="annual_report",
        )

    @staticmethod
    def _validate_pdf(body: bytes, source_filename: str) -> None:
        if not body:
            raise ValueError("empty file")
        if not source_filename.lower().endswith(".pdf"):
            raise ValueError("only PDF files are supported")

    def get_record(self, doc_id: str) -> DocumentRecord:
        with get_connection() as conn:
            record = get_pdf_document(conn, doc_id)
        if record is None:
            raise ObjectNotFoundError(f"document not found: {doc_id}")
        return record

    def list_records(self) -> list[DocumentRecord]:
        with get_connection() as conn:
            return list_pdf_documents(conn)

    def viewer_url(self, doc_id: str, *, page: int | None = None, expires_in: int = 300) -> str:
        record = self.get_record(doc_id)
        return self.store.generate_presigned_url(
            record.bucket, record.object_key, expires_in=expires_in, page=page
        )

    def local_pdf_path(self, doc_id: str) -> Path:
        record = self.get_record(doc_id)
        return self.store.resolve_local_path(record.bucket, record.object_key)

    def save_parse_artifact(
        self,
        doc_id: str,
        blocks: list[PageBlock],
        *,
        parser_backend: str = "docling",
    ) -> str:
        record = self.get_record(doc_id)
        if blocks and blocks[0].content_hash != record.content_hash:
            raise ValueError("parse result content_hash does not match uploaded PDF")
        parse_object_key, _ = self.parse_store.save_blocks(
            doc_id,
            blocks,
            source_type="pdf",
            parser_backend=parser_backend,
        )
        with get_connection() as conn:
            update_pdf_document_ingest(
                conn,
                doc_id=doc_id,
                ingest_status=record.ingest_status,
                parse_object_key=parse_object_key,
                page_count=len(blocks),
            )
            conn.commit()
        return parse_object_key

    def load_parse_artifact(
        self,
        doc_id: str,
        *,
        parser_backend: str = "docling",
    ) -> list[PageBlock]:
        record = self.get_record(doc_id)
        expected_key = self.parse_store.object_key_for(
            doc_id,
            record.content_hash,
            source_type="pdf",
            parser_backend=parser_backend,
        )
        if record.parse_object_key == expected_key:
            from app.ingest.artifact import blocks_from_json_bytes

            return blocks_from_json_bytes(self.store.get_object(record.bucket, record.parse_object_key))
        return self.parse_store.load_blocks(
            doc_id,
            record.content_hash,
            source_type="pdf",
            parser_backend=parser_backend,
        )

    def parse_artifact_viewer_url(
        self,
        doc_id: str,
        *,
        expires_in: int = 300,
        parser_backend: str = "docling",
    ) -> str:
        record = self.get_record(doc_id)
        expected_key = self.parse_store.object_key_for(
            record.doc_id,
            record.content_hash,
            source_type="pdf",
            parser_backend=parser_backend,
        )
        key = record.parse_object_key if record.parse_object_key == expected_key else expected_key
        if not self.store.object_exists(record.bucket, key):
            raise ObjectNotFoundError(f"parse artifact not found: {doc_id}")
        return self.store.generate_presigned_url(record.bucket, key, expires_in=expires_in)
