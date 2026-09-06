"""Financial Fact 数据模型（INGEST_VALIDATION.md §1）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.ingest.validation import FactKey, fact_key, normalize_amount

__all__ = [
    "FinancialFact",
    "FactKey",
    "fact_key",
    "fact_key_id",
    "normalize_amount",
    "parse_period",
    "yuan_str",
]


def yuan_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def parse_period(raw: Any) -> str:
    """报表日 → YYYY-MM-DD。"""
    if raw is None:
        raise ValueError("period is required")
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    text = str(raw).strip()
    if not text:
        raise ValueError("period is required")
    return text[:10]


def fact_key_id(key: FactKey) -> str:
    """写入 fin_metric.fact_key（VARCHAR 64）的稳定字符串。"""
    joined = "|".join(key)
    if len(joined) > 64:
        raise ValueError(f"fact_key exceeds 64 chars: {joined}")
    return joined


@dataclass
class FinancialFact:
    """一条可入库的金融事实。"""

    company_code: str
    doc_id: str
    concept: str
    period: str
    scope: str
    statement: str
    value: Decimal | None
    raw_name: str
    raw_value: str
    source_type: str = "web"
    currency: str = "CNY"
    unit_raw: str = "元"
    page_no: int | None = None
    bbox: list[float] | None = None
    parser: str = "eastmoney_f10"
    status: str = "human_review"
    review_reason: str | None = None
    xbrl_tag: str | None = None
    content_hash: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> FactKey:
        return (self.concept, self.period, self.scope, self.currency, self.statement)

    @property
    def fact_key_id(self) -> str:
        return fact_key_id(self.key)

    def to_gate_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["value"] = yuan_str(self.value)
        payload["fact_key"] = self.fact_key_id
        return payload
