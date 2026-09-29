"""聊天请求、响应与引用的数据结构。"""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc_id: str
    page: int
    snippet: str
    viewer_url: str | None = None
    title: str | None = None
    href: str | None = None
    kind: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=16000)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    session_id: str | None = None
    use_rag: bool = True
    model: str | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    disclaimer: str = "本回答由 AI 生成，仅供参考，不构成合规或投资建议。"
    citations: list[Citation] = Field(default_factory=list)
    session_id: str | None = None
    rag_used: bool = False
    route: str = "general"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    validation_trace: list[dict] = Field(default_factory=list)
    pending_request: dict | None = None
