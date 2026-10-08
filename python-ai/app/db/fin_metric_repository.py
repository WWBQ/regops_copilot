"""fin_metric 读写。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from app.ingest.facts import FinancialFact, yuan_str

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinMetricRow:
    id: int
    company_code: str | None
    doc_id: str
    source_type: str
    fact_key: str
    concept: str
    period: date
    scope: str
    currency: str
    statement: str
    value_yuan: Decimal | None
    unit_raw: str | None
    raw_name: str | None
    raw_value: str | None
    page_no: int | None
    bbox_json: Any
    parser: str | None
    status: str
    review_reason: str | None
    xbrl_tag: str | None
    content_hash: str | None
    created_at: datetime | None
    updated_at: datetime | None


def upsert_fin_metrics(conn: psycopg.Connection, facts: list[FinancialFact]) -> int:
    if not facts:
        return 0
    rows: list[tuple[Any, ...]] = []
    for fact in facts:
        rows.append(
            (
                fact.company_code,
                fact.doc_id,
                fact.source_type,
                fact.fact_key_id,
                fact.concept,
                date.fromisoformat(fact.period),
                fact.scope,
                fact.currency,
                fact.statement,
                fact.value,
                fact.unit_raw,
                fact.raw_name,
                fact.raw_value,
                fact.page_no,
                json.dumps(fact.bbox, ensure_ascii=False) if fact.bbox is not None else None,
                fact.parser,
                fact.status,
                fact.review_reason,
                fact.xbrl_tag,
                fact.content_hash,
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO fin_metric (
                company_code, doc_id, source_type, fact_key, concept, period,
                scope, currency, statement, value_yuan, unit_raw, raw_name, raw_value,
                page_no, bbox_json, parser, status, review_reason, xbrl_tag, content_hash
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s::jsonb, %s, %s, %s, %s, %s
            )
            ON CONFLICT (doc_id, fact_key) DO UPDATE SET
                company_code = EXCLUDED.company_code,
                source_type = EXCLUDED.source_type,
                concept = EXCLUDED.concept,
                period = EXCLUDED.period,
                scope = EXCLUDED.scope,
                currency = EXCLUDED.currency,
                statement = EXCLUDED.statement,
                value_yuan = CASE
                    WHEN fin_metric.status IN ('manually_accepted', 'rejected')
                     AND fin_metric.content_hash IS NOT NULL
                     AND fin_metric.content_hash = EXCLUDED.content_hash
                    THEN fin_metric.value_yuan ELSE EXCLUDED.value_yuan END,
                unit_raw = EXCLUDED.unit_raw,
                raw_name = EXCLUDED.raw_name,
                raw_value = EXCLUDED.raw_value,
                page_no = EXCLUDED.page_no,
                bbox_json = EXCLUDED.bbox_json,
                parser = EXCLUDED.parser,
                status = CASE
                    WHEN fin_metric.status IN ('manually_accepted', 'rejected')
                     AND fin_metric.content_hash IS NOT NULL
                     AND fin_metric.content_hash = EXCLUDED.content_hash
                    THEN fin_metric.status ELSE EXCLUDED.status END,
                review_reason = CASE
                    WHEN fin_metric.status IN ('manually_accepted', 'rejected')
                     AND fin_metric.content_hash IS NOT NULL
                     AND fin_metric.content_hash = EXCLUDED.content_hash
                    THEN fin_metric.review_reason ELSE EXCLUDED.review_reason END,
                xbrl_tag = EXCLUDED.xbrl_tag,
                content_hash = EXCLUDED.content_hash,
                updated_at = NOW()
            """,
            rows,
        )
    logger.info("upserted %d fin_metric rows doc_id=%s", len(rows), facts[0].doc_id)
    return len(rows)


def _row_from_db(row: tuple[Any, ...]) -> FinMetricRow:
    return FinMetricRow(
        id=int(row[0]),
        company_code=row[1],
        doc_id=row[2],
        source_type=row[3],
        fact_key=row[4],
        concept=row[5],
        period=row[6],
        scope=row[7],
        currency=row[8],
        statement=row[9],
        value_yuan=row[10],
        unit_raw=row[11],
        raw_name=row[12],
        raw_value=row[13],
        page_no=row[14],
        bbox_json=row[15],
        parser=row[16],
        status=row[17],
        review_reason=row[18],
        xbrl_tag=row[19],
        content_hash=row[20],
        created_at=row[21],
        updated_at=row[22],
    )


_SELECT = """
    SELECT id, company_code, doc_id, source_type, fact_key, concept, period,
           scope, currency, statement, value_yuan, unit_raw, raw_name, raw_value,
           page_no, bbox_json, parser, status, review_reason, xbrl_tag, content_hash,
           created_at, updated_at
    FROM fin_metric
"""


def list_fin_metrics(
    conn: psycopg.Connection,
    *,
    company_code: str | None = None,
    status: str | None = None,
    statement: str | None = None,
    concept: str | None = None,
    doc_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[FinMetricRow]:
    clauses = ["1=1"]
    params: list[Any] = []
    if company_code:
        clauses.append("company_code = %s")
        params.append(company_code)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if statement:
        clauses.append("statement = %s")
        params.append(statement)
    if concept:
        clauses.append("concept = %s")
        params.append(concept)
    if doc_id:
        clauses.append("doc_id = %s")
        params.append(doc_id)
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(
            f"{_SELECT} WHERE {' AND '.join(clauses)} "
            "ORDER BY company_code, period DESC, statement, concept LIMIT %s OFFSET %s",
            params,
        )
        return [_row_from_db(row) for row in cur.fetchall()]


def count_fin_metrics(
    conn: psycopg.Connection,
    *,
    company_code: str | None = None,
    status: str | None = None,
    statement: str | None = None,
    concept: str | None = None,
    doc_id: str | None = None,
) -> int:
    clauses = ["1=1"]
    params: list[Any] = []
    if company_code:
        clauses.append("company_code = %s")
        params.append(company_code)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if statement:
        clauses.append("statement = %s")
        params.append(statement)
    if concept:
        clauses.append("concept = %s")
        params.append(concept)
    if doc_id:
        clauses.append("doc_id = %s")
        params.append(doc_id)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM fin_metric WHERE {' AND '.join(clauses)}", params)
        return int(cur.fetchone()[0])


def list_company_metric_years(
    conn: psycopg.Connection,
    *,
    company_code: str,
    scope: str | None = None,
) -> list[int]:
    """该公司（可选口径）已入库的报告期年份，供反问/缺失时说明覆盖面。"""
    clauses = ["company_code = %s"]
    params: list[Any] = [company_code]
    if scope:
        clauses.append("scope = %s")
        params.append(scope)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT EXTRACT(YEAR FROM period)::int AS y "
            f"FROM fin_metric WHERE {' AND '.join(clauses)} ORDER BY y DESC",
            params,
        )
        return [int(row[0]) for row in cur.fetchall() if row[0] is not None]


def find_company_metrics(
    conn: psycopg.Connection,
    *,
    company_code: str,
    concept: str,
    year: int,
    scope: str = "consolidated",
) -> list[FinMetricRow]:
    """按公司 / 标准 concept / 年 / 口径取数，不限 status（由调用方过滤）。"""
    with conn.cursor() as cur:
        cur.execute(
            f"{_SELECT} WHERE company_code = %s AND concept = %s AND scope = %s "
            "AND EXTRACT(YEAR FROM period) = %s "
            "ORDER BY period DESC, statement, id",
            (company_code, concept, scope, year),
        )
        return [_row_from_db(row) for row in cur.fetchall()]


def list_all_for_gates(conn: psycopg.Connection) -> list[FinMetricRow]:
    with conn.cursor() as cur:
        cur.execute(f"{_SELECT} ORDER BY company_code, period, statement, concept")
        return [_row_from_db(row) for row in cur.fetchall()]


def list_metric_coverage(
    conn: psycopg.Connection,
    *,
    company_code: str | None = None,
    year: int | None = None,
    scope: str | None = None,
    accepted_only: bool = True,
) -> list[tuple[str, int, str, str]]:
    """覆盖面：(company_code, year, scope, concept)。供 list_scope 工具。"""
    clauses = ["company_code IS NOT NULL"]
    params: list[Any] = []
    if company_code:
        clauses.append("company_code = %s")
        params.append(company_code)
    if year is not None:
        clauses.append("EXTRACT(YEAR FROM period) = %s")
        params.append(year)
    if scope:
        clauses.append("scope = %s")
        params.append(scope)
    if accepted_only:
        clauses.append("status IN ('auto_accepted', 'manually_accepted')")
        clauses.append("value_yuan IS NOT NULL")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT company_code, EXTRACT(YEAR FROM period)::int AS y, scope, concept "
            f"FROM fin_metric WHERE {' AND '.join(clauses)} "
            "GROUP BY company_code, y, scope, concept "
            "ORDER BY company_code, y DESC, scope, concept",
            params,
        )
        return [
            (str(row[0]), int(row[1]), str(row[2]), str(row[3]))
            for row in cur.fetchall()
            if row[0] is not None and row[1] is not None
        ]


def serialize_metric(row: FinMetricRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_code": row.company_code,
        "doc_id": row.doc_id,
        "source_type": row.source_type,
        "fact_key": row.fact_key,
        "concept": row.concept,
        "period": row.period.isoformat() if isinstance(row.period, date) else row.period,
        "scope": row.scope,
        "currency": row.currency,
        "statement": row.statement,
        "value_yuan": yuan_str(row.value_yuan),
        "unit_raw": row.unit_raw,
        "raw_name": row.raw_name,
        "raw_value": row.raw_value,
        "page_no": row.page_no,
        "bbox_json": row.bbox_json,
        "parser": row.parser,
        "status": row.status,
        "review_reason": row.review_reason,
        "xbrl_tag": row.xbrl_tag,
        "content_hash": row.content_hash,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else row.created_at,
        "updated_at": row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else row.updated_at,
    }
