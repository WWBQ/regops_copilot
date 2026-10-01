"""单份 PDF：parse → clean → chunk → embed → pgvector。

批量 CLI 与 POST /ingest 共用；各阶段写入 ingest_job
（PENDING → PARSING → CLEANING → CHUNKING → EMBEDDING → DONE/FAILED）。
年报数字抽取走 F10，不经过 EXTRACTING。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.db.chunk_repository import delete_chunks, insert_chunks
from app.db.connection import get_connection
from app.db.ingest_job_repository import create_job, update_job_status
from app.db.pdf_document_repository import infer_doc_id, upsert_pdf_document
from app.documents.service import DocumentService
from app.ingest.chunker import TextChunk, chunk_page_blocks
from app.ingest.cleaner import clean_page_blocks
from app.ingest.embeddings import embed_texts, get_embedding_model
from app.ingest.models import PageBlock
from app.ingest.parser import content_hash, normalize_parser_backend, parse_pdf
from app.ingest.parse_store import ParseArtifactStore
from app.storage.local import LocalObjectStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    doc_id: str
    pages: int
    chunks: int
    deleted_chunks: int
    parse_cached: bool
    job_id: str | None = None
    parser_backend: str = "docling"


def _build_document_service() -> DocumentService:
    settings = get_settings()
    store = LocalObjectStore(
        Path(settings.object_store_root),
        default_bucket=settings.object_store_bucket,
        public_base_url=settings.api_public_base_url,
        presign_secret=settings.object_store_presign_secret,
    )
    return DocumentService(store, default_bucket=settings.object_store_bucket)


def _set_job_status(job_id: str | None, status: str, error_message: str | None = None) -> None:
    if not job_id:
        return
    with get_connection() as conn:
        update_job_status(conn, job_id=job_id, status=status, error_message=error_message)
        conn.commit()


def _ensure_job(job_id: str | None, doc_id: str) -> str:
    if job_id:
        return job_id
    with get_connection() as conn:
        created = create_job(conn, target_type="pdf", target_doc_id=doc_id, status="PENDING")
        conn.commit()
    return created


def _parse_or_load(
    pdf_path: Path,
    doc_id: str,
    *,
    use_parse_cache: bool,
    parse_store: ParseArtifactStore,
    parser_backend: str,
) -> tuple[list[PageBlock], bool]:
    file_hash = content_hash(pdf_path)
    if use_parse_cache and parse_store.exists(
        doc_id,
        file_hash,
        source_type="pdf",
        parser_backend=parser_backend,
    ):
        logger.info("load parse cache doc_id=%s backend=%s", doc_id, parser_backend)
        try:
            return (
                parse_store.load_blocks(
                    doc_id,
                    file_hash,
                    source_type="pdf",
                    parser_backend=parser_backend,
                ),
                True,
            )
        except ValueError as exc:
            logger.info("ignore stale parse cache doc_id=%s reason=%s", doc_id, exc)

    logger.info("parse pdf doc_id=%s path=%s backend=%s", doc_id, pdf_path.name, parser_backend)
    blocks = parse_pdf(pdf_path, backend=parser_backend)
    parse_store.save_blocks(
        doc_id,
        blocks,
        source_type="pdf",
        parser_backend=parser_backend,
    )
    return blocks, False


def ingest_pdf_to_vectors(
    pdf_path: Path,
    *,
    doc_id: str | None = None,
    use_parse_cache: bool = True,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    job_id: str | None = None,
    parser_backend: str | None = None,
) -> IngestResult:
    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    resolved_doc_id = doc_id or infer_doc_id(pdf_path)
    job_id = _ensure_job(job_id, resolved_doc_id)
    settings = get_settings()
    selected_parser = normalize_parser_backend(parser_backend)
    store = LocalObjectStore(
        Path(settings.object_store_root),
        default_bucket=settings.object_store_bucket,
        public_base_url=settings.api_public_base_url,
        presign_secret=settings.object_store_presign_secret,
    )
    parse_store = ParseArtifactStore(store, default_bucket=settings.object_store_bucket)
    doc_service = _build_document_service()

    try:
        body = pdf_path.read_bytes()
        upload = doc_service.upload_pdf(body, pdf_path.name, doc_id=resolved_doc_id)

        _set_job_status(job_id, "PARSING")
        blocks, parse_cached = _parse_or_load(
            pdf_path,
            resolved_doc_id,
            use_parse_cache=use_parse_cache,
            parse_store=parse_store,
            parser_backend=selected_parser,
        )
        parse_object_key = parse_store.object_key_for(
            resolved_doc_id,
            upload.content_hash,
            source_type="pdf",
            parser_backend=selected_parser,
        )

        _set_job_status(job_id, "CLEANING")
        blocks, _clean_stats = clean_page_blocks(blocks)

        _set_job_status(job_id, "CHUNKING")
        chunks: list[TextChunk] = chunk_page_blocks(
            blocks,
            doc_id=resolved_doc_id,
            source_file=pdf_path.name,
            content_hash=upload.content_hash,
            parser_backend=selected_parser,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunks:
            raise ValueError(f"no chunks produced for {pdf_path.name}")

        _set_job_status(job_id, "EMBEDDING")
        texts = [chunk.content for chunk in chunks]
        embedder = get_embedding_model()
        logger.info("embedding doc_id=%s chunks=%d", resolved_doc_id, len(texts))
        vectors = embed_texts(texts, model=embedder)

        with get_connection() as conn:
            deleted = delete_chunks(conn, doc_id=resolved_doc_id, source_type="pdf")
            inserted = insert_chunks(conn, chunks, vectors, source_type="pdf")
            upsert_pdf_document(
                conn,
                doc_id=resolved_doc_id,
                pdf_path=pdf_path,
                content_hash=upload.content_hash,
                bucket=upload.bucket,
                object_key=upload.object_key,
                page_count=len(blocks),
                parse_object_key=parse_object_key,
                ingest_status="ready",
            )
            update_job_status(conn, job_id=job_id, status="DONE")
            conn.commit()

        logger.info(
            "ingest done doc_id=%s job_id=%s backend=%s pages=%d chunks=%d deleted=%d cached=%s",
            resolved_doc_id,
            job_id,
            selected_parser,
            len(blocks),
            inserted,
            deleted,
            parse_cached,
        )
        return IngestResult(
            doc_id=resolved_doc_id,
            pages=len(blocks),
            chunks=inserted,
            deleted_chunks=deleted,
            parse_cached=parse_cached,
            job_id=job_id,
            parser_backend=selected_parser,
        )
    except Exception as exc:
        logger.exception("ingest failed doc_id=%s job_id=%s", resolved_doc_id, job_id)
        _set_job_status(job_id, "FAILED", error_message=str(exc))
        raise
