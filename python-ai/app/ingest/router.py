"""PDF 解析入口：批次上传/重解析、兼容单文件入口与同步脚本入口。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.dependencies import get_document_service
from app.db.connection import get_connection
from app.db.ingest_job_repository import create_batch, create_job, update_job_status
from app.documents.service import DocumentService
from app.ingest.parser import normalize_parser_backend
from app.ingest.pipeline import ingest_pdf_to_vectors
from app.ingest.schemas import IngestBatchRequest, IngestBatchResponse, IngestJobResponse
from app.ingest.tasks import enqueue_batch
from app.storage.exceptions import ObjectNotFoundError

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

DocSvcDep = Annotated[DocumentService, Depends(get_document_service)]


def _queue_batch(
    *, doc_ids: list[str], title: str, parser_backend: str, use_parse_cache: bool,
) -> tuple[str, list[str]]:
    if len(doc_ids) != len(set(doc_ids)):
        raise HTTPException(status_code=400, detail="同一批次不能重复选择文档")
    with get_connection() as conn:
        batch_id, job_ids = create_batch(
            conn, doc_ids=doc_ids, title=title,
            parser_backend=parser_backend, use_parse_cache=use_parse_cache,
        )
        conn.commit()
    try:
        enqueue_batch(batch_id)
    except Exception as exc:
        logger.exception("failed to publish ingest batch batch_id=%s", batch_id)
        with get_connection() as conn:
            for job_id in job_ids:
                update_job_status(
                    conn, job_id=job_id, status="FAILED", error_message="RabbitMQ 投递失败"
                )
            conn.commit()
        raise HTTPException(
            status_code=503, detail=f"解析队列不可用，批次 {batch_id} 已标记失败"
        ) from exc
    return batch_id, job_ids


@router.post("/ingest/batches", response_model=IngestBatchResponse, status_code=202)
def start_existing_documents_batch(
    body: IngestBatchRequest, service: DocSvcDep,
) -> IngestBatchResponse:
    for doc_id in body.doc_ids:
        try:
            service.local_pdf_path(doc_id)
        except (ObjectNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=f"文档不可解析：{doc_id}") from exc
    parser_backend = normalize_parser_backend(body.parser_backend)
    batch_id, _ = _queue_batch(
        doc_ids=body.doc_ids,
        title=body.title or f"年报解析 · {len(body.doc_ids)} 份",
        parser_backend=parser_backend,
        use_parse_cache=body.use_parse_cache,
    )
    return IngestBatchResponse(
        batch_id=batch_id, status="QUEUED", total_files=len(body.doc_ids), doc_ids=body.doc_ids,
    )


@router.post("/ingest/batches/upload", response_model=IngestBatchResponse, status_code=202)
async def upload_documents_batch(
    service: DocSvcDep,
    files: list[UploadFile] = File(...),
    title: str | None = Form(default=None),
    use_parse_cache: bool = Form(default=True),
    parser_backend: Literal["docling", "mineru"] | None = Form(default=None),
) -> IngestBatchResponse:
    if not 1 <= len(files) <= 50:
        raise HTTPException(status_code=400, detail="每批支持 1–50 份 PDF")
    # 先检查整批输入，再写对象存储；无效文件不应留下半批任务。
    contents = [(file.filename or "", await file.read(), file.content_type) for file in files]
    if any(not name.lower().endswith(".pdf") or not body for name, body, _ in contents):
        raise HTTPException(status_code=400, detail="文件必须是非空 PDF")
    names = [Path(name).stem for name, _, _ in contents]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="同一批次不能有同名 PDF")
    doc_ids: list[str] = []
    for name, body, content_type in contents:
        try:
            upload = service.upload_pdf(body, name, content_type=content_type or "application/pdf")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        doc_ids.append(upload.doc_id)
    if len(doc_ids) != len(set(doc_ids)):
        raise HTTPException(status_code=400, detail="同一批次的文档 ID 不能重复")
    batch_id, _ = _queue_batch(
        doc_ids=doc_ids,
        title=title or f"年报解析 · {len(doc_ids)} 份",
        parser_backend=normalize_parser_backend(parser_backend),
        use_parse_cache=use_parse_cache,
    )
    return IngestBatchResponse(
        batch_id=batch_id, status="QUEUED", total_files=len(doc_ids), doc_ids=doc_ids,
    )


@router.post("/ingest", response_model=IngestJobResponse)
async def start_pdf_ingest(
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

    if sync:
        with get_connection() as conn:
            job_id = create_job(
                conn, target_type="pdf", target_doc_id=resolved_doc_id, status="PENDING"
            )
            conn.commit()
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

    batch_id, job_ids = _queue_batch(
        doc_ids=[resolved_doc_id],
        title=f"年报解析 · {source_filename or resolved_doc_id}",
        use_parse_cache=use_parse_cache,
        parser_backend=selected_parser,
    )
    logger.info(
        "queued corpus ingest doc_id=%s job_id=%s filename=%s",
        resolved_doc_id,
        job_ids[0],
        source_filename,
    )
    return IngestJobResponse(
        job_id=job_ids[0],
        doc_id=resolved_doc_id,
        status="PENDING",
        reused=reused,
        source_filename=source_filename,
        parser_backend=selected_parser,
        message="queued",
        batch_id=batch_id,
    )
