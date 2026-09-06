"""问数引用：事实库深链 + 能唯一对上时的年报页。不估页码。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

import psycopg

from app.asknum.slots import CONCEPT_LABELS, company_display_name, concept_label
from app.db.fin_metric_repository import FinMetricRow
from app.documents.titles import format_company_report_title

logger = logging.getLogger(__name__)

_CONCEPT_NAMES: dict[str, tuple[str, ...]] = {
    "revenue": ("营业总收入", "营业收入"),
    "net_profit": ("净利润",),
    "net_profit_attributable": ("归属于母公司股东的净利润", "归属于上市公司股东的净利润"),
    "profit_before_tax": ("利润总额",),
    "income_tax": ("所得税费用", "所得税"),
    "total_assets": ("资产总计", "资产合计", "总资产"),
    "total_liabilities": ("负债合计", "负债总计", "总负债"),
    "total_equity": ("所有者权益合计", "股东权益合计", "净资产"),
    "operating_cash_flow": ("经营活动产生的现金流量净额", "经营现金流"),
    "cash_end": ("期末现金及现金等价物余额", "期末现金"),
    "cash_begin": ("期初现金及现金等价物余额", "期初现金"),
    "net_cash_change": ("现金及现金等价物净增加额",),
    "eps": ("基本每股收益", "每股收益"),
}


@dataclass(frozen=True)
class AsknumCite:
    doc_id: str
    page: int
    snippet: str
    title: str
    href: str | None = None
    kind: str = "facts"


def facts_href(
    *,
    company_code: str | None = None,
    concept: str | None = None,
    status: str | None = None,
) -> str:
    query: dict[str, str] = {}
    if company_code:
        query["company_code"] = company_code
    if concept:
        query["concept"] = concept
    if status:
        query["status"] = status
    return "/quality/facts?" + urlencode(query) if query else "/quality/facts"


def amount_needles(value: Decimal) -> list[str]:
    """用于在年报 chunk 里对金额，宁缺毋滥。"""
    integer = value.quantize(Decimal("1"))
    as_int = str(int(integer)) if integer == value.to_integral_value() else None
    needles: list[str] = []
    if as_int and len(as_int) >= 6:
        needles.append(as_int)
        needles.append(f"{int(integer):,}")
    return needles


def pick_unique_page(
    rows: list[tuple[int, str]],
    *,
    names: list[str],
    needles: list[str],
) -> tuple[int | None, str | None]:
    """名称命中且（若有）金额命中；多页不猜。"""
    pages: dict[int, str] = {}
    compact_needles = [re.sub(r"[,\s]", "", item) for item in needles]
    for page, content in rows:
        if not any(name in content for name in names):
            continue
        compact = re.sub(r"[,\s]", "", content)
        if compact_needles and not any(item in compact for item in compact_needles):
            continue
        pages.setdefault(page, content.strip()[:180])
    if len(pages) != 1:
        return None, None
    page, snippet = next(iter(pages.items()))
    return page, snippet


def find_metric_evidence_page(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    concept: str,
    raw_name: str | None,
    value_yuan: Decimal | None,
) -> tuple[int | None, str | None]:
    names = list(_CONCEPT_NAMES.get(concept, ()))
    if raw_name and any("\u4e00" <= char <= "\u9fff" for char in raw_name):
        names.insert(0, raw_name.strip())
    names = [name for name in dict.fromkeys(names) if name]
    if not doc_id or not names:
        return None, None
    needles = amount_needles(value_yuan) if value_yuan is not None else []
    if not needles:
        return None, None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE((metadata->>'page')::int, 0) AS page, content
                FROM doc_chunks
                WHERE source_type = 'pdf' AND doc_id = %s
                  AND ("""
                + " OR ".join(["content ILIKE %s"] * len(names))
                + """)
                LIMIT 40
                """,
                (doc_id, *[f"%{name}%" for name in names]),
            )
            fetched = [(int(row[0]), str(row[1] or "")) for row in cur.fetchall() if row[0]]
    except Exception:
        logger.debug("find_metric_evidence_page failed doc_id=%s", doc_id, exc_info=True)
        return None, None
    return pick_unique_page(fetched, names=names, needles=needles)


def facts_cite(
    *,
    company_code: str,
    concept: str,
    year: int,
    row: FinMetricRow | None = None,
    status: str | None = None,
    outcome: str | None = None,
) -> AsknumCite:
    label = concept_label(concept, row.raw_name if row else None)
    company = company_display_name(company_code)
    resolved_status = status or (row.status if row else None)
    doc_id = (row.doc_id if row else None) or f"{company_code}_{year}"
    bits = [f"{company} {year} 年「{label}」"]
    if resolved_status:
        bits.append(f"status={resolved_status}")
    if outcome and outcome != "ok":
        bits.append(outcome)
    if row and row.fact_key:
        bits.append(row.fact_key)
    return AsknumCite(
        doc_id=doc_id,
        page=row.page_no if row and row.page_no else 1,
        snippet="；".join(bits),
        title=f"财务事实库 · {company} {label}",
        href=facts_href(company_code=company_code, concept=concept, status=resolved_status),
        kind="facts",
    )


def document_cite(
    *,
    company_code: str,
    year: int,
    doc_id: str,
    page: int,
    snippet: str,
) -> AsknumCite:
    title = format_company_report_title(company_code=company_code, report_year=year) or doc_id
    return AsknumCite(
        doc_id=doc_id,
        page=page,
        snippet=snippet,
        title=title,
        href=None,
        kind="document",
    )


def append_markers(text: str, start_index: int, count: int) -> str:
    if count <= 0:
        return text
    marks = "".join(f"[{start_index + offset}]" for offset in range(count))
    if text.endswith("。"):
        return f"{text[:-1]} {marks}。"
    return f"{text} {marks}"


def build_lookup_cites(
    conn: psycopg.Connection | None,
    *,
    company_code: str,
    concept: str,
    year: int,
    row: FinMetricRow | None,
    outcome: str,
    value_yuan: Decimal | None = None,
) -> list[AsknumCite]:
    cites = [
        facts_cite(
            company_code=company_code,
            concept=concept,
            year=year,
            row=row,
            outcome=outcome,
        )
    ]
    if conn is None or row is None or not row.doc_id:
        return cites
    page = row.page_no
    snippet = None
    if page:
        snippet = (row.raw_name or CONCEPT_LABELS.get(concept, concept)) + "（fin_metric.page_no）"
    else:
        page, snippet = find_metric_evidence_page(
            conn,
            doc_id=row.doc_id,
            concept=concept,
            raw_name=row.raw_name,
            value_yuan=value_yuan if outcome == "ok" else None,
        )
    if page and snippet:
        cites.append(
            document_cite(
                company_code=company_code,
                year=year,
                doc_id=row.doc_id,
                page=page,
                snippet=snippet,
            )
        )
    return cites
