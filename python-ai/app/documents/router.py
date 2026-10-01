"""文档上传 / 元数据 / 预签名 viewer URL（模拟 COS 业务层）。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.dependencies import get_document_service
from app.documents.service import DocumentService
from app.documents.schemas import (
    CitationViewerRequest,
    DocumentInfoResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    ViewerUrlResponse,
)
from app.storage.exceptions import ObjectNotFoundError, ObjectStoreError

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

DocSvcDep = Annotated[DocumentService, Depends(get_document_service)]


def _info(record) -> DocumentInfoResponse:
    return DocumentInfoResponse(
        doc_id=record.doc_id,
        bucket=record.bucket,
        object_key=record.object_key,
        content_hash=record.content_hash,
        source_filename=record.source_filename,
        content_type=record.content_type,
        size=record.size,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    service: DocSvcDep,
    file: UploadFile = File(...),
    doc_id: str | None = Form(default=None),
) -> DocumentUploadResponse:
    """上传 PDF → 本地 ObjectStore（COS 等价）+ 注册 doc_id。"""
    body = await file.read()
    filename = file.filename or "upload.pdf"
    try:
        result = service.upload_pdf(body, filename, doc_id=doc_id, content_type=file.content_type or "application/pdf")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ObjectStoreError as exc:
        logger.exception("upload failed filename=%s", filename)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DocumentUploadResponse(
        doc_id=result.doc_id,
        bucket=result.bucket,
        object_key=result.object_key,
        content_hash=result.content_hash,
        source_filename=result.source_filename,
        size=result.size,
        reused=result.reused,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(service: DocSvcDep) -> DocumentListResponse:
    items = [_info(record) for record in service.list_records()]
    return DocumentListResponse(items=items)


@router.get("/{doc_id}", response_model=DocumentInfoResponse)
def get_document(doc_id: str, service: DocSvcDep) -> DocumentInfoResponse:
    try:
        return _info(service.get_record(doc_id))
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{doc_id}/content")
def stream_document_content(doc_id: str, service: DocSvcDep):
    """应用内 PDF 预览：inline 流式返回，不触发下载。"""
    from fastapi.responses import FileResponse

    try:
        record = service.get_record(doc_id)
        path = service.local_pdf_path(doc_id)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = record.source_filename or f"{doc_id}.pdf"
    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "Cache-Control": "private, max-age=120",
    }
    return FileResponse(path, media_type="application/pdf", headers=headers)


@router.get("/{doc_id}/viewer-url", response_model=ViewerUrlResponse)
def get_viewer_url(
    doc_id: str,
    service: DocSvcDep,
    page: int | None = None,
    expires_in: int = 300,
) -> ViewerUrlResponse:
    """签发短期 PDF 链接；前端打开 viewer_url 即可跳页（#page=N）。"""
    if page is not None and page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    try:
        url = service.viewer_url(doc_id, page=page, expires_in=expires_in)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ViewerUrlResponse(doc_id=doc_id, page=page, expires_in=expires_in, viewer_url=url)


@router.post("/citation/viewer-url", response_model=ViewerUrlResponse)
def citation_viewer_url(body: CitationViewerRequest, service: DocSvcDep) -> ViewerUrlResponse:
    """RAG citation 用：根据 doc_id + page 生成可点击链接。"""
    try:
        url = service.viewer_url(body.doc_id, page=body.page, expires_in=body.expires_in)
    except ObjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ViewerUrlResponse(
        doc_id=body.doc_id,
        page=body.page,
        expires_in=body.expires_in,
        viewer_url=url,
    )
