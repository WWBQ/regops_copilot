"""文档解析入库任务的数据结构。"""

from typing import Literal

from pydantic import BaseModel, Field


class IngestBatchRequest(BaseModel):
    doc_ids: list[str] = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=160)
    parser_backend: Literal["docling", "mineru"] | None = None
    use_parse_cache: bool = True


class IngestBatchResponse(BaseModel):
    batch_id: str
    status: str
    total_files: int
    doc_ids: list[str]


class IngestJobResponse(BaseModel):
    job_id: str
    doc_id: str
    status: str
    parse_cached: bool | None = None
    pages: int | None = None
    chunks: int | None = None
    reused: bool | None = None
    source_filename: str | None = None
    parser_backend: str | None = None
    message: str | None = None
    batch_id: str | None = None
