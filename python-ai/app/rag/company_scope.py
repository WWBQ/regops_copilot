"""根据问题中的公司名/股票代码/年份收窄 RAG 检索文档范围。"""

from __future__ import annotations

import re

import psycopg

_STOCK_CODE_RE = re.compile(r"\b(\d{6})\b")
_YEAR_RE = re.compile(r"(20\d{2})")
_LOOSE_YEAR_RE = re.compile(r"(20\d{2})年")
_DOC_ID_RE = re.compile(r"^(\d{6})_(\d{4})")
_YOY_SPAN_RE = re.compile(r"同比|环比|增长率|近两年|近三年|连续三年")


def is_session_doc(doc_id: str) -> bool:
    return doc_id.startswith("sess_")


def company_code_from_doc_id(doc_id: str) -> str | None:
    match = _DOC_ID_RE.match(doc_id)
    return match.group(1) if match else None


def report_year_from_doc_id(doc_id: str) -> int | None:
    match = _DOC_ID_RE.match(doc_id)
    return int(match.group(2)) if match else None


def _normalize_year_text(question: str) -> str:
    text = re.sub(r"(\d+)\s+年", r"\1年", question.strip())
    return re.sub(r"024年", "2024年", text)


def mentioned_company_codes(question: str) -> set[str]:
    """问题中出现的证券代码（简称或 6 位数字）。"""
    from app.asknum.aliases import company_aliases

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


def _years_needed(question: str, year: int | None) -> set[int] | None:
    """问句写了年份时默认只留该年；同比/近两年带上一年。"""
    if year is None:
        return None
    years = {year}
    if _YOY_SPAN_RE.search(question):
        years.add(year - 1)
        if "近三年" in question or "连续三年" in question:
            years.add(year - 2)
    return years


def _apply_company_year_rows(
    rows: list[tuple[str, str | None, int | None]],
    question: str,
) -> list[str]:
    if not rows:
        return []
    normalized = _normalize_year_text(question)
    codes = mentioned_company_codes(normalized)
    year = mentioned_report_year(normalized)
    if not codes and year is None:
        return [row[0] for row in rows]

    filtered = list(rows)
    if codes:
        filtered = [row for row in filtered if row[1] in codes]
        if not filtered:
            return []
    wanted_years = _years_needed(normalized, year)
    if wanted_years is not None:
        year_rows = [row for row in filtered if row[2] in wanted_years]
        if year_rows:
            filtered = year_rows
        elif codes:
            return []
    return [row[0] for row in filtered]


def filter_doc_ids_by_question(doc_ids: list[str], question: str) -> list[str]:
    """不连库：会话文档始终保留；年报按 doc_id 里的代码/年份裁剪。"""
    if not doc_ids:
        return []
    session_ids = [doc_id for doc_id in doc_ids if is_session_doc(doc_id)]
    corpus_rows = [
        (doc_id, company_code_from_doc_id(doc_id), report_year_from_doc_id(doc_id))
        for doc_id in doc_ids
        if not is_session_doc(doc_id)
    ]
    scoped = _apply_company_year_rows(corpus_rows, question)
    return session_ids + scoped


def filter_doc_ids_for_question(
    conn: psycopg.Connection,
    doc_ids: list[str],
    question: str,
) -> list[str]:
    """优先读 pdf_document 元数据；读不到则回退 doc_id 解析。"""
    if not doc_ids:
        return doc_ids

    session_ids = [doc_id for doc_id in doc_ids if is_session_doc(doc_id)]
    corpus_ids = [doc_id for doc_id in doc_ids if not is_session_doc(doc_id)]
    if not corpus_ids:
        return session_ids

    rows: list[tuple[str, str | None, int | None]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, company_code, report_year
                FROM pdf_document
                WHERE doc_id = ANY(%s)
                  AND is_active = TRUE
                  AND ingest_status = 'ready'
                """,
                (corpus_ids,),
            )
            rows = [(str(row[0]), row[1], row[2]) for row in cur.fetchall()]
    except Exception:
        rows = []

    if not rows:
        return filter_doc_ids_by_question(doc_ids, question)

    scoped = _apply_company_year_rows(rows, question)
    return session_ids + scoped
