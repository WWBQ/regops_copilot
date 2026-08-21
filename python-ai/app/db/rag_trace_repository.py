"""rag_query_log 读写。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from app.rag.trace import RagTrace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagQueryLogRow:
    id: int
    request_id: str | None
    session_id: str | None
    question: str
    outcome: str
    rag_used: bool
    keyword_terms: list[str]
    scoped_doc_ids: list[str]
    vector_hit_count: int
    keyword_hit_count: int
    final_hit_count: int
    max_vector_score: float | None
    min_score_threshold: float | None
    total_rag_ms: float
    hits: list[dict[str, Any]]
    pipeline: dict[str, Any]
    created_at: datetime


def insert_rag_trace(conn: psycopg.Connection, trace: RagTrace) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_query_log (
                request_id, session_id, question, outcome, rag_used,
                keyword_terms, scoped_doc_ids,
                vector_hit_count, keyword_hit_count, final_hit_count,
                max_vector_score, min_score_threshold, total_rag_ms,
                hits, pipeline
            )
            VALUES (
                %s, %s::uuid, %s, %s, %s,
                %s::jsonb, %s::jsonb,
                %s, %s, %s,
                %s, %s, %s,
                %s::jsonb, %s::jsonb
            )
            RETURNING id
            """,
            (
                trace.request_id,
                trace.session_id,
                trace.question,
                trace.outcome,
                trace.rag_used,
                json.dumps(trace.keyword_terms, ensure_ascii=False),
                json.dumps(trace.scoped_doc_ids, ensure_ascii=False),
                trace.vector_hit_count,
                trace.keyword_hit_count,
                trace.final_hit_count,
                trace.max_vector_score,
                trace.min_score_threshold,
                trace.total_rag_ms,
                json.dumps(trace.hits, ensure_ascii=False),
                json.dumps(trace.pipeline, ensure_ascii=False),
            ),
        )
        row_id = int(cur.fetchone()[0])
    logger.info(
        "rag_trace saved id=%d outcome=%s rag_used=%s ms=%.1f",
        row_id,
        trace.outcome,
        trace.rag_used,
        trace.total_rag_ms,
    )
    return row_id


def _row_from_db(row: tuple[Any, ...]) -> RagQueryLogRow:
    return RagQueryLogRow(
        id=int(row[0]),
        request_id=row[1],
        session_id=str(row[2]) if row[2] is not None else None,
        question=row[3],
        outcome=row[4],
        rag_used=bool(row[5]),
        keyword_terms=row[6] if isinstance(row[6], list) else json.loads(row[6] or "[]"),
        scoped_doc_ids=row[7] if isinstance(row[7], list) else json.loads(row[7] or "[]"),
        vector_hit_count=int(row[8]),
        keyword_hit_count=int(row[9]),
        final_hit_count=int(row[10]),
        max_vector_score=float(row[11]) if row[11] is not None else None,
        min_score_threshold=float(row[12]) if row[12] is not None else None,
        total_rag_ms=float(row[13] or 0),
        hits=row[14] if isinstance(row[14], list) else json.loads(row[14] or "[]"),
        pipeline=row[15] if isinstance(row[15], dict) else json.loads(row[15] or "{}"),
        created_at=row[16],
    )


def list_rag_traces(
    conn: psycopg.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    outcome: str | None = None,
) -> list[RagQueryLogRow]:
    clauses = ["1=1"]
    params: list[Any] = []
    if outcome:
        clauses.append("outcome = %s")
        params.append(outcome)
    params.extend([limit, offset])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, request_id, session_id, question, outcome, rag_used,
                   keyword_terms, scoped_doc_ids,
                   vector_hit_count, keyword_hit_count, final_hit_count,
                   max_vector_score, min_score_threshold, total_rag_ms,
                   hits, pipeline, created_at
            FROM rag_query_log
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [_row_from_db(row) for row in rows]


def get_rag_trace(conn: psycopg.Connection, trace_id: int) -> RagQueryLogRow | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, request_id, session_id, question, outcome, rag_used,
                   keyword_terms, scoped_doc_ids,
                   vector_hit_count, keyword_hit_count, final_hit_count,
                   max_vector_score, min_score_threshold, total_rag_ms,
                   hits, pipeline, created_at
            FROM rag_query_log
            WHERE id = %s
            """,
            (trace_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return _row_from_db(row)


def count_rag_traces(conn: psycopg.Connection, *, outcome: str | None = None) -> int:
    clauses = ["1=1"]
    params: list[Any] = []
    if outcome:
        clauses.append("outcome = %s")
        params.append(outcome)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM rag_query_log WHERE {' AND '.join(clauses)}",
            params,
        )
        return int(cur.fetchone()[0])
