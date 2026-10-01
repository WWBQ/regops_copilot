from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.db.pdf_document_repository import DocumentRecord


@pytest.fixture
def document_repository_stub(monkeypatch):
    """让文档 API 单测只测业务逻辑，不依赖本机 PostgreSQL。"""
    records: dict[str, DocumentRecord] = {}

    class Connection:
        def commit(self) -> None:
            pass

    @contextmanager
    def connection():
        yield Connection()

    def get_document(_conn, doc_id: str):
        return records.get(doc_id)

    def upsert_document(_conn, **values):
        now = datetime.now(UTC).isoformat()
        current = records.get(values["doc_id"])
        records[values["doc_id"]] = DocumentRecord(
            doc_id=values["doc_id"],
            bucket=values["bucket"],
            object_key=values["object_key"],
            content_hash=values["content_hash"],
            source_filename=values["source_filename"],
            content_type=values["content_type"],
            size=values["file_size"],
            parse_object_key=values.get("parse_object_key") or (
                current.parse_object_key if current else None
            ),
            created_at=current.created_at if current else now,
            updated_at=now,
            doc_type=values.get("doc_type") or "annual_report",
            ingest_status=values.get("ingest_status", "uploaded"),
            meta=values.get("meta") or {},
        )

    def update_document(_conn, *, doc_id: str, **values):
        current = records[doc_id]
        records[doc_id] = replace(
            current,
            parse_object_key=values.get("parse_object_key") or current.parse_object_key,
            ingest_status=values["ingest_status"],
            updated_at=datetime.now(UTC).isoformat(),
        )

    monkeypatch.setattr("app.documents.service.get_connection", connection)
    monkeypatch.setattr("app.documents.service.get_pdf_document", get_document)
    monkeypatch.setattr("app.documents.service.upsert_uploaded_pdf_document", upsert_document)
    monkeypatch.setattr("app.documents.service.update_pdf_document_ingest", update_document)
    monkeypatch.setattr(
        "app.documents.service.list_pdf_documents",
        lambda _conn: [row for row in records.values() if row.doc_type != "session_upload"],
    )
    return records
