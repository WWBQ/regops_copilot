from __future__ import annotations

"""金融风险初筛的结构化输出契约。

Agent 仍然先输出适合用户阅读的 Markdown，并在末尾追加一个
``risk_audit_result`` JSON 代码块。运行时在同一次模型调用结束后解析该代码块，
校验证据编号，再把 Markdown 与结构化结果分别交给前端和业务数据库。
"""

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RISK_RESULT_BLOCK = re.compile(
    r"(?:\n|^)```risk_audit_result\s*(\{.*?\})\s*```\s*$",
    re.DOTALL,
)


class RiskFinding(BaseModel):
    """一条有证据支撑、等待人工复核的风险线索。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    risk_type: str = Field(min_length=1, max_length=80)
    severity: Literal["low", "medium", "high"]
    conclusion: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[int] = Field(min_length=1)
    data_points: list[str] = Field(default_factory=list)
    uncertainty: str = Field(min_length=1, max_length=1000)
    review_question: str = Field(min_length=1, max_length=1000)


class RiskAuditResult(BaseModel):
    """一次金融风险初筛的机器可读结果。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_code: str = Field(min_length=1, max_length=32)
    company_name: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1990, le=2100)
    status: Literal["completed", "partial", "insufficient_evidence"]
    findings: list[RiskFinding] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def validate_evidence_state(self) -> "RiskAuditResult":
        if self.status == "insufficient_evidence" and self.findings:
            raise ValueError("insufficient_evidence 状态不能同时输出风险线索")
        if self.status == "insufficient_evidence" and not self.evidence_gaps:
            raise ValueError("证据不足时必须说明 evidence_gaps")
        return self


def answer_hash(markdown: str) -> str:
    """生成用于把数据库结果重新关联到历史回答的稳定摘要。"""

    normalized = " ".join((markdown or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def strip_risk_result_block(text: str) -> str:
    """删除回答末尾的机器 JSON，只保留用户可见 Markdown。"""

    return RISK_RESULT_BLOCK.sub("", text or "").strip()


def parse_risk_audit_output(
    text: str,
    *,
    available_citation_ids: set[int] | None = None,
) -> tuple[str, RiskAuditResult | None, str | None]:
    """解析并校验一次 Agent 最终输出。

    结构化块缺失或不合法时不伪造结果：保留 Markdown，返回错误原因，由调用方记录
    日志并继续向用户交付自然语言回答。
    """

    raw_text = text or ""
    match = RISK_RESULT_BLOCK.search(raw_text)
    if match is None:
        return raw_text.strip(), None, "missing_structured_result"
    markdown = raw_text[: match.start()].strip()
    try:
        payload: Any = json.loads(match.group(1))
        result = RiskAuditResult.model_validate(payload)
    except (ValueError, TypeError) as exc:
        return markdown, None, f"invalid_structured_result: {exc}"

    if available_citation_ids is not None:
        referenced = {
            citation_id
            for finding in result.findings
            for citation_id in finding.evidence_ids
        }
        unknown = sorted(referenced - available_citation_ids)
        if unknown:
            return markdown, None, f"unknown_citation_ids: {unknown}"

    return markdown, result, None
