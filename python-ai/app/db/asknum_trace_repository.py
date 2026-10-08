"""asknum_query_log 读写。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AsknumQueryLogRow:
    id: int
    request_id: str | None
    session_id: str | None
    question: str
    route: str
    company_codes: list[str]
    concepts: list[str]
    year: int | None
    year_defaulted: bool
    scope: str | None
    narrative: bool
    lookups: list[dict[str, Any]]
    total_ms: float
    created_at: datetime


def insert_asknum_trace(conn: psycopg.Connection, trace: Any) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO asknum_query_log (
                request_id, session_id, user_id, question, route,
                company_codes, concepts, year, year_defaulted, scope,
                narrative, lookups, total_ms
            )
            VALUES (
                %s, %s::uuid, %s::uuid, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s, %s,
                %s, %s::jsonb, %s
            )
            RETURNING id
            """,
            (
                trace.request_id,
                trace.session_id,
                trace.user_id,
                trace.question,
                trace.route,
                json.dumps(trace.company_codes, ensure_ascii=False),
                json.dumps(trace.concepts, ensure_ascii=False),
                trace.year,
                trace.year_defaulted,
                trace.scope,
                trace.narrative,
                json.dumps(trace.lookups, ensure_ascii=False),
                trace.total_ms,
            ),
        )
        row_id = int(cur.fetchone()[0])
    logger.info(
        "asknum_trace saved id=%d route=%s ms=%.1f",
        row_id,
        trace.route,
        trace.total_ms,
    )
    return row_id


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return json.loads(value or "[]")


def _row_from_db(row: tuple[Any, ...]) -> AsknumQueryLogRow:
    return AsknumQueryLogRow(
        id=int(row[0]),
        request_id=row[1],
        session_id=str(row[2]) if row[2] is not None else None,
        question=row[3],
        route=row[4],
        company_codes=_as_list(row[5]),
        concepts=_as_list(row[6]),
        year=int(row[7]) if row[7] is not None else None,
        year_defaulted=bool(row[8]),
        scope=row[9],
        narrative=bool(row[10]),
        lookups=_as_list(row[11]),
        total_ms=float(row[12] or 0),
        created_at=row[13],
    )


_SELECT = """
    SELECT id, request_id, session_id, question, route,
           company_codes, concepts, year, year_defaulted, scope,
           narrative, lookups, total_ms, created_at
    FROM asknum_query_log
"""


def list_asknum_traces(
    conn: psycopg.Connection,
    *,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    route: str | None = None,
) -> list[AsknumQueryLogRow]:
    clauses = ["user_id = %s::uuid"]
    params: list[Any] = [user_id]
    if route:
        clauses.append("route = %s")
        params.append(route)
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            {_SELECT}
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [_row_from_db(row) for row in rows]


def get_asknum_trace(conn: psycopg.Connection, trace_id: int, *, user_id: str) -> AsknumQueryLogRow | None:
    with conn.cursor() as cur:
        cur.execute(f"{_SELECT} WHERE id = %s AND user_id = %s::uuid", (trace_id, user_id))
        row = cur.fetchone()
    if not row:
        return None
    return _row_from_db(row)


def summarize_asknum_traces(conn: psycopg.Connection, *, user_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT route, COUNT(*), COALESCE(AVG(total_ms), 0)
            FROM asknum_query_log
            WHERE user_id = %s::uuid
            GROUP BY route
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    by_route: dict[str, int] = {}
    total = 0
    weighted_ms = 0.0
    for route, count, avg_ms in rows:
        n = int(count)
        by_route[str(route)] = n
        total += n
        weighted_ms += float(avg_ms) * n
    return {
        "total": total,
        "by_route": by_route,
        "avg_ms": round(weighted_ms / total, 1) if total else 0.0,
        "metric_count": by_route.get("metric", 0),
        "blocked_count": by_route.get("metric_blocked", 0),
        "clarify_count": by_route.get("metric_clarify", 0),
        "skip_count": by_route.get("skip", 0),
    }


def count_asknum_traces(conn: psycopg.Connection, *, user_id: str, route: str | None = None) -> int:
    clauses = ["user_id = %s::uuid"]
    params: list[Any] = [user_id]
    if route:
        clauses.append("route = %s")
        params.append(route)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM asknum_query_log WHERE {' AND '.join(clauses)}",
            params,
        )
        return int(cur.fetchone()[0])
