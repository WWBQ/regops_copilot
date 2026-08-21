from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateResponse(BaseModel):
    session_id: str
    expires_at: datetime | None = None


class SessionDocumentResponse(BaseModel):
    doc_id: str
    source_filename: str
    job_id: str | None = None
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionDocumentListResponse(BaseModel):
    session_id: str
    items: list[SessionDocumentResponse]


class SessionDocumentUploadResponse(BaseModel):
    session_id: str
    doc_id: str
    job_id: str
    status: str = "PENDING"
    source_filename: str
    message: str = Field(
        default="已接收 PDF，正在后台解析入库（本会话有效，约需数分钟）"
    )
