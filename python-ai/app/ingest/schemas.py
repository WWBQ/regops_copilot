"""文档解析入库任务的数据结构。"""

from pydantic import BaseModel


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
