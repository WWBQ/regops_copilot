"""Chat 会话：创建 / 上传 PDF / 查询 ingest 状态。"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.api.deps import get_document_service
from app.db.connection import get_connection
from app.db.ingest_job_repository import create_job
from app.db.session_repository import (
    attach_document,
    create_session,
    get_document_row,
    list_session_documents,
    session_exists,
)
from app.documents.service import DocumentService
from app.ingest.session_pipeline import ingest_session_pdf
from app.schemas.sessions import (
    SessionCreateResponse,
    SessionDocumentListResponse,
    SessionDocumentResponse,
    SessionDocumentUploadResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)

DocSvcDep = Annotated[DocumentService, Depends(get_document_service)]


def _parse_session_id(session_id: str) -> str:
    try:
        return str(UUID(session_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid session_id") from exc


def _ensure_session(session_id: str) -> str:
    session_id = _parse_session_id(session_id)
    with get_connection() as conn:
        if not session_exists(conn, session_id):
            raise HTTPException(status_code=404, detail="session not found")
    return session_id


@router.post("", response_model=SessionCreateResponse)
def create_chat_session() -> SessionCreateResponse:
    with get_connection() as conn:
        session_id = create_session(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT expires_at FROM chat_session WHERE session_id = %s::uuid",
            (session_id,),
        )
        expires_at = cur.fetchone()[0]
        conn.commit()
    return SessionCreateResponse(session_id=session_id, expires_at=expires_at)


@router.get("/{session_id}/documents", response_model=SessionDocumentListResponse)
def list_documents(session_id: str) -> SessionDocumentListResponse:
    session_id = _ensure_session(session_id)
    with get_connection() as conn:
        rows = list_session_documents(conn, session_id)
    items = [
        SessionDocumentResponse(
            doc_id=row.doc_id,
            source_filename=row.source_filename,
            job_id=row.job_id,
            status=row.status,
            page_count=row.page_count,
            chunk_count=row.chunk_count,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
    return SessionDocumentListResponse(session_id=session_id, items=items)


@router.get("/{session_id}/documents/{doc_id}", response_model=SessionDocumentResponse)
def get_document_status(session_id: str, doc_id: str) -> SessionDocumentResponse:
    session_id = _ensure_session(session_id)
    with get_connection() as conn:
        row = get_document_row(conn, session_id=session_id, doc_id=doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found in session")
    return SessionDocumentResponse(
        doc_id=row.doc_id,
        source_filename=row.source_filename,
        job_id=row.job_id,
        status=row.status,
        page_count=row.page_count,
        chunk_count=row.chunk_count,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_session_ingest(
    *,
    session_id: str,
    job_id: str,
    body: bytes,
    source_filename: str,
) -> None:
    try:
        ingest_session_pdf(
            session_id=session_id,
            job_id=job_id,
            body=body,
            source_filename=source_filename,
        )
    except Exception:
        logger.exception("background session ingest failed session_id=%s job_id=%s", session_id, job_id)


@router.post("/{session_id}/documents", response_model=SessionDocumentUploadResponse)
async def upload_session_document(
    session_id: str,
    background_tasks: BackgroundTasks,
    service: DocSvcDep,
    file: UploadFile = File(...),
) -> SessionDocumentUploadResponse:
    session_id = _ensure_session(session_id)
    body = await file.read()
    source_filename = file.filename or "upload.pdf"
    if not source_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are supported")
    if not body:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        upload = service.upload_session_pdf(body, source_filename, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with get_connection() as conn:
        job_id = create_job(
            conn,
            target_type="pdf",
            target_doc_id=upload.doc_id,
            status="PENDING",
        )
        attach_document(
            conn,
            session_id=session_id,
            doc_id=upload.doc_id,
            source_filename=source_filename,
            job_id=job_id,
            status="PENDING",
        )
        conn.commit()

    background_tasks.add_task(
        _run_session_ingest,
        session_id=session_id,
        job_id=job_id,
        body=body,
        source_filename=source_filename,
    )
    logger.info(
        "queued session ingest session_id=%s doc_id=%s job_id=%s filename=%s",
        session_id,
        upload.doc_id,
        job_id,
        source_filename,
    )
    return SessionDocumentUploadResponse(
        session_id=session_id,
        doc_id=upload.doc_id,
        job_id=job_id,
        status="PENDING",
        source_filename=source_filename,
    )
