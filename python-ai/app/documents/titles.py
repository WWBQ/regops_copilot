"""文档展示标题（引用 hover / 弹层用，非文件名）。"""

from __future__ import annotations

import psycopg

# 证券代码 → 公司简称（用于年报标题展示）
COMPANY_DISPLAY_NAMES: dict[str, str] = {
    "002594": "比亚迪",
    "000333": "美的集团",
    "000651": "格力电器",
    "600031": "三一重工",
    "601633": "长城汽车",
    "300750": "宁德时代",
    "600519": "贵州茅台",
}

_DOC_TYPE_LABELS: dict[str, str] = {
    "annual_report": "年度报告",
    "semi_annual": "半年度报告",
    "interim": "中期报告",
}


def format_company_report_title(
    *,
    company_code: str | None,
    report_year: int | None,
    doc_type: str = "annual_report",
) -> str | None:
    if not company_code or not report_year:
        return None
    company = COMPANY_DISPLAY_NAMES.get(company_code, f"({company_code})")
    doc_label = _DOC_TYPE_LABELS.get(doc_type, "报告")
    return f"{company}{report_year}年{doc_label}"


def resolve_document_titles(conn: psycopg.Connection, doc_ids: list[str]) -> dict[str, str]:
    """批量解析 doc_id → 展示标题。"""
    if not doc_ids:
        return {}

    unique = list(dict.fromkeys(doc_ids))
    titles: dict[str, str] = {}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, title, source_filename, company_code, report_year, doc_type
            FROM pdf_document
            WHERE doc_id = ANY(%s) AND is_active = TRUE
            """,
            (unique,),
        )
        for doc_id, _title, source_filename, company_code, report_year, doc_type in cur.fetchall():
            display = format_company_report_title(
                company_code=company_code,
                report_year=report_year,
                doc_type=doc_type or "annual_report",
            )
            if display:
                titles[doc_id] = display
            elif _title and not str(_title).endswith(".pdf"):
                titles[doc_id] = str(_title)

        missing = [doc_id for doc_id in unique if doc_id not in titles]
        if missing:
            cur.execute(
                """
                SELECT DISTINCT ON (doc_id) doc_id, source_filename
                FROM session_document
                WHERE doc_id = ANY(%s)
                ORDER BY doc_id, updated_at DESC NULLS LAST
                """,
                (missing,),
            )
            for doc_id, source_filename in cur.fetchall():
                # 会话上传：去掉扩展名，仍比 doc_id 可读
                stem = source_filename.rsplit(".", 1)[0] if source_filename else doc_id
                titles[doc_id] = stem

    for doc_id in unique:
        titles.setdefault(doc_id, doc_id)

    return titles
