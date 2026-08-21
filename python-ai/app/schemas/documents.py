"""文档 API 模型。"""

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    doc_id: str
    bucket: str
    object_key: str
    content_hash: str
    source_filename: str
    size: int
    reused: bool


class DocumentInfoResponse(BaseModel):
    doc_id: str
    bucket: str
    object_key: str
    content_hash: str
    source_filename: str
    content_type: str
    size: int
    created_at: str
    updated_at: str


class ViewerUrlResponse(BaseModel):
    doc_id: str
    page: int | None = None
    expires_in: int
    viewer_url: str


class DocumentListResponse(BaseModel):
    items: list[DocumentInfoResponse]


class CitationViewerRequest(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=128)
    page: int = Field(..., ge=1)
    expires_in: int = Field(default=300, ge=30, le=3600)
