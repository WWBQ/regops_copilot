"""根据问题中的公司名/股票代码/年份收窄 RAG 检索文档范围。"""

from __future__ import annotations

import re

import psycopg

from app.asknum.aliases import company_aliases

_STOCK_CODE_RE = re.compile(r"\b(\d{6})\b")
_YEAR_RE = re.compile(r"(20\d{2})")
_LOOSE_YEAR_RE = re.compile(r"(20\d{2})年")


def _normalize_year_text(question: str) -> str:
    text = re.sub(r"(\d+)\s+年", r"\1年", question.strip())
    return re.sub(r"024年", "2024年", text)


def mentioned_company_codes(question: str) -> set[str]:
    """问题中出现的证券代码（简称或 6 位数字）。"""
    codes: set[str] = set(_STOCK_CODE_RE.findall(question))
    lowered = question.casefold()
    for alias, code in company_aliases().items():
        if alias.casefold() in lowered:
            codes.add(code)
    return codes


def mentioned_report_year(question: str) -> int | None:
    normalized = _normalize_year_text(question)
    match = _LOOSE_YEAR_RE.search(normalized) or _YEAR_RE.search(normalized)
    if not match:
        return None
    return int(match.group(1))


def filter_doc_ids_for_question(
    conn: psycopg.Connection,
    doc_ids: list[str],
    question: str,
) -> list[str]:
    """若问题含明确公司/年份，优先只检索对应年报，避免跨公司噪声。"""
    if not doc_ids:
        return doc_ids

    normalized = _normalize_year_text(question)
    codes = mentioned_company_codes(normalized)
    year = mentioned_report_year(normalized)
    if not codes and year is None:
        return doc_ids

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, company_code, report_year
            FROM pdf_document
            WHERE doc_id = ANY(%s)
              AND is_active = TRUE
              AND ingest_status = 'ready'
            """,
            (doc_ids,),
        )
        rows = cur.fetchall()

    if not rows:
        return doc_ids

    if codes:
        rows = [row for row in rows if row[1] in codes]
    if year is not None:
        year_rows = [row for row in rows if row[2] == year]
        if year_rows:
            rows = year_rows

    if not rows:
        return doc_ids

    scoped = [row[0] for row in rows]
    return scoped
