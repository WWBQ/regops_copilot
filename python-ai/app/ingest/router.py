"""批量 PDF ingest：POST /ingest + ingest_job 状态查询。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.core.dependencies import get_document_service
from app.db.connection import get_connection
from app.db.ingest_job_repository import create_job
from app.documents.service import DocumentService
from app.ingest.parser import normalize_parser_backend
from app.ingest.pipeline import ingest_pdf_to_vectors
from app.ingest.schemas import IngestJobResponse
from app.storage.exceptions import ObjectNotFoundError

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

DocSvcDep = Annotated[DocumentService, Depends(get_document_service)]


def _run_corpus_ingest(
    *,
    pdf_path: Path,
    doc_id: str,
    job_id: str,
    use_parse_cache: bool,
    parser_backend: str | None,
) -> None:
    try:
        ingest_pdf_to_vectors(
            pdf_path,
            doc_id=doc_id,
            job_id=job_id,
            use_parse_cache=use_parse_cache,
            parser_backend=parser_backend,
        )
    except Exception:
        logger.exception("background corpus ingest failed doc_id=%s job_id=%s", doc_id, job_id)


@router.post("/ingest", response_model=IngestJobResponse)
async def start_pdf_ingest(
    background_tasks: BackgroundTasks,
    service: DocSvcDep,
    file: UploadFile | None = File(default=None),
    doc_id: str | None = Form(default=None),
    use_parse_cache: bool = Form(default=True),
    parser_backend: Literal["docling", "mineru"] | None = Form(default=None),
    sync: bool = Form(default=False),
) -> IngestJobResponse:
    """上传或按已有 doc_id 触发批量 ingest，写入 ingest_job 全阶段状态。"""
    selected_parser = normalize_parser_backend(parser_backend)
    resolved_doc_id: str | None = doc_id.strip() if doc_id else None
    source_filename: str | None = None
    reused = False

    if file is not None and file.filename:
        body = await file.read()
        source_filename = file.filename
        if not source_filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="only PDF files are supported")
        if not body:
            raise HTTPException(status_code=400, detail="empty file")
        try:
            upload = service.upload_pdf(
                body,
                source_filename,
                doc_id=resolved_doc_id,
                content_type=file.content_type or "application/pdf",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        resolved_doc_id = upload.doc_id
        reused = upload.reused
        source_filename = upload.source_filename

    if not resolved_doc_id:
        raise HTTPException(status_code=400, detail="file or doc_id is required")

    try:
        pdf_path = service.local_pdf_path(resolved_doc_id)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with get_connection() as conn:
        job_id = create_job(
            conn,
            target_type="pdf",
            target_doc_id=resolved_doc_id,
            status="PENDING",
        )
        conn.commit()

    if sync:
        result = ingest_pdf_to_vectors(
            pdf_path,
            doc_id=resolved_doc_id,
            job_id=job_id,
            use_parse_cache=use_parse_cache,
            parser_backend=selected_parser,
        )
        return IngestJobResponse(
            job_id=job_id,
            doc_id=result.doc_id,
            status="DONE",
            parse_cached=result.parse_cached,
            pages=result.pages,
            chunks=result.chunks,
            reused=reused,
            source_filename=source_filename,
            parser_backend=result.parser_backend,
        )

    background_tasks.add_task(
        _run_corpus_ingest,
        pdf_path=pdf_path,
        doc_id=resolved_doc_id,
        job_id=job_id,
        use_parse_cache=use_parse_cache,
        parser_backend=selected_parser,
    )
    logger.info(
        "queued corpus ingest doc_id=%s job_id=%s filename=%s",
        resolved_doc_id,
        job_id,
        source_filename,
    )
    return IngestJobResponse(
        job_id=job_id,
        doc_id=resolved_doc_id,
        status="PENDING",
        reused=reused,
        source_filename=source_filename,
        parser_backend=selected_parser,
        message="queued",
    )
