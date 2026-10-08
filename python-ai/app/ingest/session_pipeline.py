"""会话级 PDF ingest：parse → chunk → embed，与正式文档共用 doc_chunks。"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from app.config import get_settings
from app.db.chunk_repository import delete_chunks, insert_chunks
from app.db.connection import get_connection
from app.db.ingest_job_repository import update_job_status
from app.db.pdf_document_repository import update_pdf_document_ingest
from app.db.session_repository import update_document_status
from app.documents.service import DocumentService
from app.ingest.chunker import TextChunk, chunk_page_blocks
from app.ingest.cleaner import clean_page_blocks
from app.ingest.embeddings import embed_texts, get_embedding_model
from app.ingest.models import PageBlock
from app.ingest.parser import normalize_parser_backend, parse_pdf
from app.ingest.parse_store import ParseArtifactStore
from app.storage.local import LocalObjectStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionIngestResult:
    doc_id: str
    pages: int
    chunks: int
    parse_cached: bool


def _build_document_service() -> DocumentService:
    settings = get_settings()
    store = LocalObjectStore(
        Path(settings.object_store_root),
        default_bucket=settings.object_store_bucket,
        public_base_url=settings.api_public_base_url,
        presign_secret=settings.object_store_presign_secret,
    )
    return DocumentService(store, default_bucket=settings.object_store_bucket)


def _parse_pdf_bytes(
    body: bytes,
    *,
    source_filename: str,
    parser_backend: str,
) -> list[PageBlock]:
    suffix = Path(source_filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)
    try:
        return parse_pdf(tmp_path, backend=parser_backend)
    finally:
        tmp_path.unlink(missing_ok=True)


def _with_session_metadata(chunks: list[TextChunk], *, session_id: str) -> list[TextChunk]:
    return [
        replace(
            chunk,
            metadata={
                **chunk.metadata,
                "session_id": session_id,
                "scope": "session",
            },
        )
        for chunk in chunks
    ]


def ingest_session_pdf(
    *,
    session_id: str,
    job_id: str,
    body: bytes,
    source_filename: str,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
) -> SessionIngestResult:
    """同步执行会话 ingest；由解析 Worker 调用。"""
    doc_service = _build_document_service()
    settings = get_settings()
    store = LocalObjectStore(
        Path(settings.object_store_root),
        default_bucket=settings.object_store_bucket,
        public_base_url=settings.api_public_base_url,
        presign_secret=settings.object_store_presign_secret,
    )
    parse_store = ParseArtifactStore(store, default_bucket=settings.object_store_bucket)
    parser_backend = normalize_parser_backend(settings.document_parser_backend)

    upload = doc_service.upload_session_pdf(body, source_filename, session_id=session_id)
    doc_id = upload.doc_id

    def _set_status(job_status: str, doc_status: str) -> None:
        with get_connection() as conn:
            update_job_status(conn, job_id=job_id, status=job_status)
            update_document_status(conn, session_id=session_id, doc_id=doc_id, status=doc_status)
            update_pdf_document_ingest(conn, doc_id=doc_id, ingest_status="processing")
            conn.commit()

    try:
        _set_status("PARSING", "PROCESSING")

        parse_cached = False
        if parse_store.exists(
            doc_id,
            upload.content_hash,
            source_type="pdf",
            parser_backend=parser_backend,
        ):
            try:
                blocks = parse_store.load_blocks(
                    doc_id,
                    upload.content_hash,
                    source_type="pdf",
                    parser_backend=parser_backend,
                )
                parse_cached = True
            except ValueError as exc:
                logger.info("ignore stale session parse cache doc_id=%s reason=%s", doc_id, exc)
                blocks = _parse_pdf_bytes(
                    body,
                    source_filename=source_filename,
                    parser_backend=parser_backend,
                )
                parse_store.save_blocks(
                    doc_id,
                    blocks,
                    source_type="pdf",
                    parser_backend=parser_backend,
                )
        else:
            blocks = _parse_pdf_bytes(
                body,
                source_filename=source_filename,
                parser_backend=parser_backend,
            )
            parse_store.save_blocks(
                doc_id,
                blocks,
                source_type="pdf",
                parser_backend=parser_backend,
            )

        _set_status("CLEANING", "PROCESSING")
        blocks, _ = clean_page_blocks(blocks)

        _set_status("CHUNKING", "PROCESSING")
        chunks: list[TextChunk] = chunk_page_blocks(
            blocks,
            doc_id=doc_id,
            source_file=source_filename,
            content_hash=upload.content_hash,
            parser_backend=parser_backend,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunks = _with_session_metadata(chunks, session_id=session_id)
        if not chunks:
            raise ValueError(f"no chunks produced for {source_filename}")

        _set_status("EMBEDDING", "PROCESSING")
        vectors = embed_texts([chunk.content for chunk in chunks], model=get_embedding_model())
        parse_object_key = parse_store.object_key_for(
            doc_id,
            upload.content_hash,
            source_type="pdf",
            parser_backend=parser_backend,
        )
        with get_connection() as conn:
            delete_chunks(conn, doc_id=doc_id, source_type="pdf")
            inserted = insert_chunks(conn, chunks, vectors, source_type="pdf")
            update_pdf_document_ingest(
                conn,
                doc_id=doc_id,
                ingest_status="ready",
                parse_object_key=parse_object_key,
                page_count=len(blocks),
            )
            update_job_status(conn, job_id=job_id, status="DONE")
            update_document_status(
                conn,
                session_id=session_id,
                doc_id=doc_id,
                status="READY",
                page_count=len(blocks),
                chunk_count=inserted,
            )
            conn.commit()

        logger.info(
            "session ingest done session_id=%s doc_id=%s pages=%d chunks=%d cached=%s",
            session_id,
            doc_id,
            len(blocks),
            inserted,
            parse_cached,
        )
        return SessionIngestResult(
            doc_id=doc_id,
            pages=len(blocks),
            chunks=inserted,
            parse_cached=parse_cached,
        )
    except Exception as exc:
        logger.exception("session ingest failed session_id=%s doc_id=%s", session_id, doc_id)
        with get_connection() as conn:
            update_pdf_document_ingest(conn, doc_id=doc_id, ingest_status="failed")
            update_job_status(conn, job_id=job_id, status="FAILED", error_message=str(exc))
            update_document_status(
                conn,
                session_id=session_id,
                doc_id=doc_id,
                status="FAILED",
                error_message=str(exc),
            )
            conn.commit()
        raise
