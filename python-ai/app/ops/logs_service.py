"""结构化日志事件：从 ingest / session / RAG 表聚合。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.connection import get_connection

OUTCOME_LEVEL: dict[str, str] = {
    "ok": "info",
    "no_intent": "info",
    "no_docs": "warn",
    "low_score": "warn",
    "pending_docs": "warn",
}

OUTCOME_MESSAGE: dict[str, str] = {
    "ok": "RAG 检索成功",
    "no_intent": "未识别合规意图，跳过 RAG",
    "no_docs": "无可用文档范围",
    "low_score": "检索分数低于阈值",
    "pending_docs": "会话文档仍在解析中",
}


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
        return cur.fetchone()[0] is not None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _ingest_job_events(conn, *, source_filter: str | None, level_filter: str | None) -> list[dict[str, Any]]:
    if source_filter and source_filter != "ingest":
        return []
    if not _table_exists(conn, "ingest_job"):
        return []

    events: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT job_id::text, target_type, target_doc_id, status,
                   error_message, created_at, updated_at
            FROM ingest_job
            WHERE status = 'FAILED' OR error_message IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 200
            """
        )
        for row in cur.fetchall():
            level = "error" if row[3] == "FAILED" else "warn"
            if level_filter and level != level_filter:
                continue
            message = row[4] or f"ingest_job {row[3]}"
            events.append(
                {
                    "id": f"ingest:{row[0]}",
                    "source": "ingest",
                    "level": level,
                    "message": message,
                    "detail": {
                        "job_id": row[0],
                        "target_type": row[1],
                        "target_doc_id": row[2],
                        "status": row[3],
                    },
                    "occurred_at": _iso(row[6] or row[5]),
                }
            )
    return events


def _session_events(conn, *, source_filter: str | None, level_filter: str | None) -> list[dict[str, Any]]:
    if source_filter and source_filter != "session":
        return []
    if not _table_exists(conn, "session_document"):
        return []

    events: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id::text, doc_id, source_filename, status,
                   error_message, updated_at
            FROM session_document
            WHERE status = 'FAILED' OR error_message IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 200
            """
        )
        for row in cur.fetchall():
            level = "error" if row[3] == "FAILED" else "warn"
            if level_filter and level != level_filter:
                continue
            message = row[4] or f"会话上传 {row[3]}: {row[2]}"
            events.append(
                {
                    "id": f"session:{row[0]}:{row[1]}",
                    "source": "session",
                    "level": level,
                    "message": message,
                    "detail": {
                        "session_id": row[0],
                        "doc_id": row[1],
                        "source_filename": row[2],
                        "status": row[3],
                    },
                    "occurred_at": _iso(row[5]),
                }
            )
    return events


def _rag_events(conn, *, source_filter: str | None, level_filter: str | None) -> list[dict[str, Any]]:
    if source_filter and source_filter != "rag":
        return []
    if not _table_exists(conn, "rag_query_log"):
        return []

    events: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, request_id, session_id::text, question, outcome,
                   total_rag_ms, created_at
            FROM rag_query_log
            WHERE outcome <> 'ok'
            ORDER BY created_at DESC
            LIMIT 300
            """
        )
        for row in cur.fetchall():
            outcome = str(row[4])
            level = OUTCOME_LEVEL.get(outcome, "info")
            if level_filter and level != level_filter:
                continue
            question = str(row[3] or "")
            snippet = question if len(question) <= 120 else question[:117] + "..."
            events.append(
                {
                    "id": f"rag:{row[0]}",
                    "source": "rag",
                    "level": level,
                    "message": f"{OUTCOME_MESSAGE.get(outcome, outcome)} · {snippet}",
                    "detail": {
                        "trace_id": int(row[0]),
                        "request_id": row[1],
                        "session_id": row[2],
                        "outcome": outcome,
                        "total_rag_ms": row[5],
                    },
                    "occurred_at": _iso(row[6]),
                }
            )
    return events


def list_log_events(
    *,
    limit: int = 50,
    offset: int = 0,
    source: str | None = None,
    level: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        events: list[dict[str, Any]] = []
        events.extend(_ingest_job_events(conn, source_filter=source, level_filter=level))
        events.extend(_session_events(conn, source_filter=source, level_filter=level))
        events.extend(_rag_events(conn, source_filter=source, level_filter=level))

    events.sort(key=lambda item: item.get("occurred_at") or "", reverse=True)
    total = len(events)
    page = events[offset : offset + limit]

    summary: dict[str, int] = {"error": 0, "warn": 0, "info": 0}
    by_source: dict[str, int] = {"ingest": 0, "session": 0, "rag": 0}
    for event in events:
        summary[event["level"]] = summary.get(event["level"], 0) + 1
        by_source[event["source"]] = by_source.get(event["source"], 0) + 1

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "summary": {"by_level": summary, "by_source": by_source},
        "items": page,
    }
