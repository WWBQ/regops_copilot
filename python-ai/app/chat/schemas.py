"""聊天请求、响应与引用的数据结构。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class ComparisonClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(..., min_length=1, max_length=2000)
    citation_ids: list[int] = Field(..., min_length=1)


class ComparisonCompanyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_code: str = Field(..., pattern=r"^\d{6}$")
    company_name: str = Field(..., min_length=1, max_length=100)
    summary: str = Field(..., min_length=1, max_length=4000)
    citation_ids: list[int] = Field(..., min_length=1)


class CompanyComparisonResult(BaseModel):
    """多公司叙述性比较的模型输出契约。"""

    model_config = ConfigDict(extra="forbid")

    answer_type: Literal["company_comparison"]
    comparison_allowed: bool
    periods: list[int] = Field(..., min_length=1)
    companies: list[ComparisonCompanyResult] = Field(..., min_length=2)
    similarities: list[ComparisonClaim] = Field(default_factory=list)
    differences: list[ComparisonClaim] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


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
    # 仅最终回答模型调用耗时。
    latency_ms: float = 0.0
    # 从请求进入 Python 到响应完成的端到端耗时。
    total_latency_ms: float = 0.0
    validation_trace: list[dict] = Field(default_factory=list)
    pending_request: dict | None = None
    comparison: CompanyComparisonResult | None = None
