"""运维：RAG 检索 trace 查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.asknum_trace_repository import (
    count_asknum_traces,
    get_asknum_trace,
    list_asknum_traces,
    summarize_asknum_traces,
)
from app.db.connection import get_connection
from app.db.rag_trace_repository import count_rag_traces, get_rag_trace, list_rag_traces

router = APIRouter(prefix="/ops", tags=["ops"])


def _serialize_row(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "session_id": row.session_id,
        "question": row.question,
        "outcome": row.outcome,
        "rag_used": row.rag_used,
        "keyword_terms": row.keyword_terms,
        "scoped_doc_ids": row.scoped_doc_ids,
        "vector_hit_count": row.vector_hit_count,
        "keyword_hit_count": row.keyword_hit_count,
        "final_hit_count": row.final_hit_count,
        "max_vector_score": row.max_vector_score,
        "min_score_threshold": row.min_score_threshold,
        "total_rag_ms": row.total_rag_ms,
        "hits": row.hits,
        "pipeline": row.pipeline,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else row.created_at,
    }


@router.get("/rag/overview")
def rag_overview_api() -> dict[str, Any]:
    from app.ops.rag_service import fetch_rag_overview

    return fetch_rag_overview()


@router.get("/rag-traces")
def list_rag_trace_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    outcome: str | None = Query(None),
) -> dict[str, Any]:
    from app.ops.rag_service import fetch_rag_overview

    with get_connection() as conn:
        rows = list_rag_traces(conn, limit=limit, offset=offset, outcome=outcome)
        total = count_rag_traces(conn, outcome=outcome)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_row(row) for row in rows],
        "summary": fetch_rag_overview(),
    }


@router.get("/rag-traces/{trace_id}")
def get_rag_trace_api(trace_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = get_rag_trace(conn, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="rag trace not found")
    return _serialize_row(row)


def _serialize_asknum_row(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "session_id": row.session_id,
        "question": row.question,
        "route": row.route,
        "company_codes": row.company_codes,
        "concepts": row.concepts,
        "year": row.year,
        "year_defaulted": row.year_defaulted,
        "scope": row.scope,
        "narrative": row.narrative,
        "lookups": row.lookups,
        "total_ms": row.total_ms,
        "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else row.created_at,
    }


@router.get("/asknum-traces")
def list_asknum_trace_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    route: str | None = Query(None),
) -> dict[str, Any]:
    with get_connection() as conn:
        rows = list_asknum_traces(conn, limit=limit, offset=offset, route=route)
        total = count_asknum_traces(conn, route=route)
        summary = summarize_asknum_traces(conn)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_asknum_row(row) for row in rows],
        "summary": summary,
    }


@router.get("/asknum-traces/{trace_id}")
def get_asknum_trace_api(trace_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = get_asknum_trace(conn, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asknum trace not found")
    return _serialize_asknum_row(row)


@router.get("/system/overview")
def system_overview_api() -> dict[str, Any]:
    from app.ops.system_service import fetch_system_overview

    return fetch_system_overview()


@router.get("/ingest/overview")
def ingest_overview_api() -> dict[str, Any]:
    from app.ops.ingest_service import fetch_ingest_overview

    return fetch_ingest_overview()


@router.get("/ingest/jobs")
def list_ingest_jobs_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    target_type: str | None = Query(None),
) -> dict[str, Any]:
    from app.ops.ingest_service import list_ingest_jobs

    return list_ingest_jobs(
        limit=limit,
        offset=offset,
        status=status,
        target_type=target_type,
    )


@router.get("/ingest/session-documents")
def list_session_ingest_documents_api(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
) -> dict[str, Any]:
    from app.ops.ingest_service import list_session_ingest_documents

    return list_session_ingest_documents(limit=limit, offset=offset, status=status)


@router.get("/logs/events")
def list_log_events_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: str | None = Query(None),
    level: str | None = Query(None),
) -> dict[str, Any]:
    from app.ops.logs_service import list_log_events

    return list_log_events(limit=limit, offset=offset, source=source, level=level)


@router.get("/obs/overview")
def obs_overview_api() -> dict[str, Any]:
    from app.obs.generations import overview

    return overview()


@router.get("/obs/traces")
def obs_traces_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    from app.obs.generations import list_generations, overview

    payload = list_generations(limit=limit, offset=offset)
    payload["summary"] = overview()
    return payload
