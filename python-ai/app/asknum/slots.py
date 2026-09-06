"""问数槽位：公司、指标、期间、口径。规则抽取，不调 LLM。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.asknum.aliases import concept_aliases
from app.documents.titles import COMPANY_DISPLAY_NAMES
from app.rag.company_scope import mentioned_company_codes, mentioned_report_year

DEFAULT_REPORT_YEAR = 2024
DEFAULT_SCOPE = "consolidated"

_NARRATIVE_RE = re.compile(
    r"为什么|为何|原因|怎么解释|如何解释|怎么看|怎么样|"
    r"是否违规|是否合规|"
    r"风险因素|内控|战略|展望|车型|新车|新品"
)

# 像在问数、但标准别名没打中时，用来反问而不是漏去 RAG
_AMOUNT_INTENT_RE = re.compile(
    r"多少|几亿|几万|是多少|有多少|查一下|查一查|告诉我|数字|业绩"
)
_METRIC_HINT_RE = re.compile(
    r"利润|营收|净利|资产|负债|权益|现金流|每股|eps|财报|财务"
)
# 故意不入库、不手算：继续走 RAG，不要反问「请指定营收/净利润」
_UNSUPPORTED_RATIO_RE = re.compile(
    r"roe|净资产收益率|毛利率|净利率|销售净利率|销售毛利率|"
    r"研发投入|研发费用|研发强度",
    re.IGNORECASE,
)
_UNSUPPORTED_PERIOD_RE = re.compile(
    r"同比|环比|增长率|一季度|二季度|三季度|四季度|"
    r"[Qq][1-4]|第[一二三四]季|半年报|中报|近三年|近两年|连续三年"
)
_LAST_YEAR_RE = re.compile(r"去年|上年")
_THIS_YEAR_RE = re.compile(r"今年|本年")

CONCEPT_LABELS: dict[str, str] = {
    "revenue": "营业收入",
    "net_profit": "净利润",
    "net_profit_attributable": "归属于母公司股东的净利润",
    "profit_before_tax": "利润总额",
    "income_tax": "所得税费用",
    "total_assets": "资产总计",
    "total_liabilities": "负债合计",
    "total_equity": "所有者权益合计",
    "operating_cash_flow": "经营活动产生的现金流量净额",
    "cash_end": "期末现金及现金等价物余额",
    "cash_begin": "期初现金及现金等价物余额",
    "net_cash_change": "现金及现金等价物净增加额",
    "eps": "基本每股收益",
}

SCOPE_LABELS: dict[str, str] = {
    "consolidated": "合并报表",
    "parent": "母公司报表",
}


@dataclass(frozen=True)
class AsknumSlots:
    company_codes: tuple[str, ...]
    concepts: tuple[str, ...]
    year: int
    year_defaulted: bool
    scope: str
    narrative: bool


def parse_concepts(question: str) -> list[str]:
    found: list[str] = []
    remaining = question.casefold()
    for alias, concept in sorted(concept_aliases(), key=lambda item: len(item[0]), reverse=True):
        needle = alias.casefold()
        if needle in remaining:
            if concept not in found:
                found.append(concept)
            remaining = remaining.replace(needle, " ", 1)
    return found


def parse_scope(question: str) -> str:
    if "母公司" in question:
        return "parent"
    return DEFAULT_SCOPE


def has_amount_intent(question: str) -> bool:
    return bool(_AMOUNT_INTENT_RE.search(question))


def looks_like_metric_question(question: str) -> bool:
    """像在问数：认不出标准别名时也不该丢给 RAG 猜数。"""
    if _NARRATIVE_RE.search(question):
        return False
    if is_unsupported_ratio(question) or has_unsupported_period(question):
        return True
    if has_amount_intent(question):
        return True
    if mentioned_company_codes(question) and _METRIC_HINT_RE.search(question):
        return True
    return False


def is_unsupported_ratio(question: str) -> bool:
    return bool(_UNSUPPORTED_RATIO_RE.search(question))


def has_unsupported_period(question: str) -> bool:
    return bool(_UNSUPPORTED_PERIOD_RE.search(question))


def parse_relative_year(question: str) -> int | None:
    """相对年锚在默认报告期（当前库只有 2024），不跟日历年走。"""
    if _LAST_YEAR_RE.search(question):
        return DEFAULT_REPORT_YEAR - 1
    if _THIS_YEAR_RE.search(question):
        return DEFAULT_REPORT_YEAR
    return None


def parse_slots(question: str) -> AsknumSlots:
    text = question.strip()
    year = mentioned_report_year(text)
    relative = parse_relative_year(text)
    resolved = year if year is not None else relative
    codes = tuple(sorted(mentioned_company_codes(text)))
    return AsknumSlots(
        company_codes=codes,
        concepts=tuple(parse_concepts(text)),
        year=resolved if resolved is not None else DEFAULT_REPORT_YEAR,
        year_defaulted=year is None and relative is None,
        scope=parse_scope(text),
        narrative=bool(_NARRATIVE_RE.search(text)),
    )


def company_display_name(code: str) -> str:
    return COMPANY_DISPLAY_NAMES.get(code, code)


def concept_label(concept: str, raw_name: str | None = None) -> str:
    name = (raw_name or "").strip()
    if name and any("\u4e00" <= char <= "\u9fff" for char in name):
        return name
    return CONCEPT_LABELS.get(concept, concept)
