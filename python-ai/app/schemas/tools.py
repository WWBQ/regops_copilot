"""W5 工具合同：入参 / 出参。先 Function Calling，MCP 只换传输。"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.compliance import ComplianceConclusion

ConceptName = Literal[
    "revenue",
    "net_profit",
    "net_profit_attributable",
    "profit_before_tax",
    "income_tax",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "operating_cash_flow",
    "cash_end",
    "cash_begin",
    "net_cash_change",
    "eps",
]
ScopeName = Literal["consolidated", "parent"]
LookupOutcome = Literal["ok", "human_review", "missing", "accepted_conflict", "not_accepted"]
VerifyVerdict = Literal["match", "mismatch", "unavailable"]


class LookupMetricArgs(BaseModel):
    company_code: str = Field(..., pattern=r"^\d{6}$", description="6 位证券代码")
    year: int = Field(..., ge=2000, le=2100)
    scope: ScopeName = "consolidated"
    concept: ConceptName | None = Field(default=None, description="单科时可用；与 concepts 二选一")
    concepts: list[ConceptName] | None = Field(
        default=None,
        min_length=1,
        max_length=5,
        description="一次 1–5 个科目。单科传一个元素即可",
    )

    @model_validator(mode="after")
    def normalize_concepts(self) -> LookupMetricArgs:
        items = list(self.concepts or [])
        if self.concept:
            if items and self.concept not in items:
                raise ValueError("concept 与 concepts 不一致")
            if not items:
                items = [self.concept]
        if not items:
            raise ValueError("必须提供 concept 或 concepts")
        if len(items) != len(set(items)):
            raise ValueError("concepts 不能重复")
        if len(items) > 5:
            raise ValueError("一次最多查询 5 个科目")
        self.concepts = items  # type: ignore[assignment]
        self.concept = items[0]  # type: ignore[assignment]
        return self


class LookupMetricResult(BaseModel):
    ok: bool
    stop: bool
    outcome: LookupOutcome
    company_code: str
    concept: str
    year: int
    scope: str
    value_yuan: str | None = None
    raw_name: str | None = None
    fact_key: str | None = None
    doc_id: str | None = None
    status: str | None = None
    review_reason: str | None = None
    message: str


class LookupMetricsResult(BaseModel):
    ok: bool
    stop: bool
    company_code: str
    year: int
    scope: str
    lookups: list[LookupMetricResult]
    message: str


class ListScopeArgs(BaseModel):
    company_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    year: int | None = Field(default=None, ge=2000, le=2100)
    scope: ScopeName | None = None
    accepted_only: bool = True


class ScopeItem(BaseModel):
    company_code: str
    company_name: str
    year: int
    scope: str
    concepts: list[str]


class ListScopeResult(BaseModel):
    ok: bool
    stop: bool
    companies: list[str]
    years: list[int]
    items: list[ScopeItem]
    message: str


class RagSearchArgs(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class RagSearchHit(BaseModel):
    doc_id: str
    page: int = Field(..., ge=1)
    snippet: str
    title: str | None = None
    viewer_url: str | None = None


class RagSearchResult(BaseModel):
    ok: bool
    stop: bool
    outcome: str
    citations: list[RagSearchHit] = Field(default_factory=list)
    message: str


class VerifyNumberArgs(BaseModel):
    company_code: str = Field(..., pattern=r"^\d{6}$")
    concept: ConceptName
    year: int = Field(..., ge=2000, le=2100)
    scope: ScopeName = "consolidated"
    claimed: str = Field(..., min_length=1, max_length=64, description="声称金额，元或带亿/万")

    @field_validator("claimed")
    @classmethod
    def claimed_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("claimed 不能为空")
        return cleaned


class VerifyNumberResult(BaseModel):
    ok: bool
    stop: bool
    verdict: VerifyVerdict
    lookup_outcome: LookupOutcome
    claimed_yuan: str | None = None
    fact_yuan: str | None = None
    message: str


class ComparePeersArgs(BaseModel):
    company_codes: list[str] = Field(..., min_length=2, max_length=5)
    concept: ConceptName
    year: int = Field(..., ge=2000, le=2100)
    scope: ScopeName = "consolidated"

    @field_validator("company_codes")
    @classmethod
    def company_codes_unique_digits(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for code in value:
            item = code.strip()
            if not re.fullmatch(r"\d{6}", item):
                raise ValueError("company_codes 必须是 6 位证券代码")
            cleaned.append(item)
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("company_codes 不能重复")
        return cleaned


class ComparePeersResult(BaseModel):
    ok: bool
    stop: bool
    concept: str
    year: int
    scope: str
    lookups: list[LookupMetricResult]
    message: str


class CreateReviewDraftArgs(BaseModel):
    company_code: str = Field(..., pattern=r"^\d{6}$")
    title: str = Field(..., min_length=1, max_length=120)
    reason: str = Field(..., min_length=1, max_length=500)
    company_codes: list[str] = Field(default_factory=list)
    conclusion: str = Field(default="", max_length=2000)
    risk_level: str | None = Field(default=None, max_length=8)
    clause_refs: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    impact_scope: str = Field(default="", max_length=500)
    thread_id: str | None = Field(default=None, max_length=80)
    session_id: str | None = None
    request_id: str | None = Field(default=None, max_length=64)
    dept: str | None = Field(default=None, max_length=32)

    @field_validator("company_codes")
    @classmethod
    def _codes(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for code in value:
            item = code.strip()
            if not re.fullmatch(r"\d{6}", item):
                raise ValueError("company_codes 必须是 6 位证券代码")
            if item not in cleaned:
                cleaned.append(item)
        return cleaned


class CreateReviewDraftResult(BaseModel):
    ok: bool
    stop: bool
    message: str
    draft_id: str | None = None
    status: str | None = None
    replayed: bool = False


class EmitConclusionArgs(ComplianceConclusion):
    """与合规 DTO 同一套约束：条款至少一条，高风险 confidence≤0.95。"""


class EmitConclusionResult(BaseModel):
    ok: bool
    stop: bool
    conclusion: ComplianceConclusion
    message: str


ToolErrorCode = Literal[
    "unknown_tool",
    "invalid_params",
    "missing",
    "unauthorized",
    "timeout",
    "handler_error",
    "forbidden_write",
    "budget_exceeded",
]
ToolInject = Literal["missing", "unauthorized", "timeout"]


class ToolContext(BaseModel):
    """调用上下文。Mock 用来注入越权/超时/幂等；live 目前只透传日志。"""

    dept: str | None = None
    actor: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
    inject: ToolInject | None = None
    request_id: str | None = None
    backend: Literal["live", "mock"] | None = None


class ToolInvokeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    dept: str | None = None
    actor: str | None = None
    idempotency_key: str | None = None
    inject: ToolInject | None = None
    backend: Literal["live", "mock"] | None = None


class ToolInvokeResponse(BaseModel):
    name: str
    ok: bool
    stop: bool
    result: dict[str, Any]
    error: str | None = None
    error_code: ToolErrorCode | None = None
    replayed: bool = False
    request_id: str | None = None
