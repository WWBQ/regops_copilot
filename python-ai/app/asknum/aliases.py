"""别名表：近义词 → 标准指标 / 证券代码。优先读 asknum_alias，读不到用内置兜底。"""

from __future__ import annotations

import logging
import time

from app.db.asknum_alias_repository import list_asknum_aliases
from app.db.connection import get_connection

logger = logging.getLogger(__name__)

# 与 docs/sql/w4_asknum_alias.sql 种子一致；表不存在或为空时用它。
BUILTIN_CONCEPT_ALIASES: tuple[tuple[str, str], ...] = (
    ("经营活动产生的现金流量净额", "operating_cash_flow"),
    ("现金及现金等价物净增加额", "net_cash_change"),
    ("期末现金及现金等价物余额", "cash_end"),
    ("期初现金及现金等价物余额", "cash_begin"),
    ("归属于母公司股东的净利润", "net_profit_attributable"),
    ("归属于母公司所有者的净利润", "net_profit_attributable"),
    ("所有者权益合计", "total_equity"),
    ("股东权益合计", "total_equity"),
    ("营业总收入", "revenue"),
    ("营业收入", "revenue"),
    ("经营现金流", "operating_cash_flow"),
    ("经营性现金流", "operating_cash_flow"),
    ("利润总额", "profit_before_tax"),
    ("所得税费用", "income_tax"),
    ("基本每股收益", "eps"),
    ("每股收益", "eps"),
    ("资产总计", "total_assets"),
    ("资产合计", "total_assets"),
    ("负债合计", "total_liabilities"),
    ("负债总计", "total_liabilities"),
    ("归母净利润", "net_profit_attributable"),
    ("归母净利", "net_profit_attributable"),
    ("赚了多少钱", "net_profit"),
    ("挣了多少钱", "net_profit"),
    ("盈利多少", "net_profit"),
    ("赚多少", "net_profit"),
    ("净赚", "net_profit"),
    ("进账", "revenue"),
    ("卖货", "revenue"),
    ("家底", "total_assets"),
    ("手头现金", "cash_end"),
    ("账面现金", "cash_end"),
    ("归母", "net_profit_attributable"),
    ("总资产", "total_assets"),
    ("总负债", "total_liabilities"),
    ("净资产", "total_equity"),
    ("股东权益", "total_equity"),
    ("所得税", "income_tax"),
    ("净利润", "net_profit"),
    ("期末现金", "cash_end"),
    ("期初现金", "cash_begin"),
    ("卖了多少", "revenue"),
    ("营收", "revenue"),
    ("净利", "net_profit"),
    ("赚钱", "net_profit"),
    ("挣钱", "net_profit"),
    ("赚了", "net_profit"),
    ("eps", "eps"),
)

BUILTIN_COMPANY_ALIASES: dict[str, str] = {
    "比亚迪股份": "002594",
    "比亚迪": "002594",
    "byd": "002594",
    "美的集团": "000333",
    "美的电器": "000333",
    "美的": "000333",
    "格力电器": "000651",
    "格力股份": "000651",
    "格力": "000651",
    "长城汽车": "601633",
    "长城股份": "601633",
    "长城": "601633",
    "三一重工": "600031",
    "三一集团": "600031",
    "三一": "600031",
    "宁德时代": "300750",
    "宁德": "300750",
    "贵州茅台": "600519",
    "茅台": "600519",
}

_CACHE_TTL_SEC = 30.0
_cache_concepts: tuple[tuple[str, str], ...] | None = None
_cache_companies: dict[str, str] | None = None
_cache_at = 0.0


def clear_alias_cache() -> None:
    global _cache_concepts, _cache_companies, _cache_at
    _cache_concepts = None
    _cache_companies = None
    _cache_at = 0.0


def _load_from_db() -> tuple[tuple[tuple[str, str], ...], dict[str, str]] | None:
    try:
        with get_connection() as conn:
            rows = list_asknum_aliases(conn, enabled_only=True)
    except Exception:
        logger.debug("asknum_alias unavailable, using builtins", exc_info=True)
        return None
    if not rows:
        return None
    concepts = tuple((alias, target) for kind, alias, target in rows if kind == "concept")
    companies = {alias: target for kind, alias, target in rows if kind == "company"}
    if not concepts and not companies:
        return None
    return concepts or BUILTIN_CONCEPT_ALIASES, companies or BUILTIN_COMPANY_ALIASES


def _refresh() -> None:
    global _cache_concepts, _cache_companies, _cache_at
    loaded = _load_from_db()
    if loaded is None:
        _cache_concepts = BUILTIN_CONCEPT_ALIASES
        _cache_companies = dict(BUILTIN_COMPANY_ALIASES)
    else:
        _cache_concepts, _cache_companies = loaded
    _cache_at = time.monotonic()


def _ensure_cache() -> None:
    if _cache_concepts is None or (time.monotonic() - _cache_at) > _CACHE_TTL_SEC:
        _refresh()


def concept_aliases() -> tuple[tuple[str, str], ...]:
    _ensure_cache()
    assert _cache_concepts is not None
    return _cache_concepts


def company_aliases() -> dict[str, str]:
    _ensure_cache()
    assert _cache_companies is not None
    return _cache_companies
