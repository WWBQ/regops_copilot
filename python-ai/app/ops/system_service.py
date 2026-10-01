"""系统概览：服务、语料库、入库、RAG 统计。"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.db.connection import get_connection
from app.eval.registry import load_all_tasks

logger = logging.getLogger(__name__)


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
        return cur.fetchone()[0] is not None


def _safe_query(conn, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_system_overview() -> dict[str, Any]:
    settings = get_settings()
    checked_at = datetime.now(timezone.utc).isoformat()

    overview: dict[str, Any] = {
        "checked_at": checked_at,
        "services": {
            "python_ai": {"status": "ok", "service": "regops-python-ai"},
            "postgresql": {"status": "unknown", "latency_ms": None, "error": None},
            "pgvector": {"status": "unknown", "installed": False},
        },
        "corpus": {
            "documents": [],
            "ready_count": 0,
            "total_chunks": 0,
            "total_pages": 0,
        },
        "ingest_jobs": [],
        "sessions": {
            "session_count": 0,
            "pending_documents": 0,
        },
        "rag_traces": {
            "total": 0,
            "last_24h": 0,
            "by_outcome": {},
        },
        "eval": {
            "task_count": len(load_all_tasks()),
        },
        "config": {
            "default_model": settings.default_model,
            "embedding_model": settings.embedding_model,
            "rag_top_k": settings.rag_top_k,
            "rag_compare_rerank_candidates": settings.rag_compare_rerank_candidates,
            "rag_compare_top_k_per_company": settings.rag_compare_top_k_per_company,
            "rag_rerank_enabled": settings.rag_rerank_enabled,
            "rag_rerank_backend": settings.rag_rerank_backend,
            "rag_rerank_model": (
                settings.rag_llm_rerank_model
                if settings.rag_rerank_backend == "llm"
                else settings.rag_rerank_model
            ),
            "rag_llm_rerank_deployment": (
                settings.rag_llm_rerank_deployment
                if settings.rag_rerank_backend == "llm"
                else None
            ),
            "rag_llm_rerank_base_url": (
                settings.rag_llm_rerank_base_url
                if settings.rag_rerank_backend == "llm"
                else None
            ),
            "rag_trace_enabled": settings.rag_trace_enabled,
        },
    }

    try:
        with get_connection() as conn:
            t0 = time.perf_counter()
            _safe_query(conn, "SELECT 1")
            overview["services"]["postgresql"] = {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "error": None,
            }

            rows = _safe_query(
                conn,
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')",
            )
            installed = bool(rows[0][0]) if rows else False
            overview["services"]["pgvector"] = {
                "status": "ok" if installed else "missing",
                "installed": installed,
            }

            if _table_exists(conn, "pdf_document"):
                doc_rows = _safe_query(
                    conn,
                    """
                    SELECT p.doc_id, p.company_code, p.report_year, p.page_count,
                           p.ingest_status, p.updated_at,
                           COALESCE(c.chunk_count, 0) AS chunk_count
                    FROM pdf_document p
                    LEFT JOIN (
                        SELECT doc_id, COUNT(*) AS chunk_count
                        FROM doc_chunks
                        GROUP BY doc_id
                    ) c ON c.doc_id = p.doc_id
                    WHERE p.is_active = TRUE
                    ORDER BY p.company_code, p.report_year DESC
                    """,
                )
                documents = []
                ready_count = 0
                total_pages = 0
                for row in doc_rows:
                    status = row[4]
                    if status == "ready":
                        ready_count += 1
                    pages = int(row[3] or 0)
                    total_pages += pages
                    updated = row[5]
                    documents.append(
                        {
                            "doc_id": row[0],
                            "company_code": row[1],
                            "report_year": row[2],
                            "page_count": pages,
                            "ingest_status": status,
                            "chunk_count": int(row[6] or 0),
                            "updated_at": updated.isoformat() if updated else None,
                        }
                    )
                overview["corpus"]["documents"] = documents
                overview["corpus"]["ready_count"] = ready_count
                overview["corpus"]["total_pages"] = total_pages

            if _table_exists(conn, "doc_chunks"):
                rows = _safe_query(conn, "SELECT COUNT(*) FROM doc_chunks")
                overview["corpus"]["total_chunks"] = int(rows[0][0]) if rows else 0

            if _table_exists(conn, "ingest_job"):
                job_rows = _safe_query(
                    conn,
                    """
                    SELECT job_id::text, target_type, target_doc_id, status,
                           error_message, created_at, updated_at, finished_at
                    FROM ingest_job
                    ORDER BY created_at DESC
                    LIMIT 15
                    """,
                )
                overview["ingest_jobs"] = [
                    {
                        "job_id": row[0],
                        "target_type": row[1],
                        "target_doc_id": row[2],
                        "status": row[3],
                        "error_message": row[4],
                        "created_at": row[5].isoformat() if row[5] else None,
                        "updated_at": row[6].isoformat() if row[6] else None,
                        "finished_at": row[7].isoformat() if row[7] else None,
                    }
                    for row in job_rows
                ]

            if _table_exists(conn, "chat_session"):
                rows = _safe_query(conn, "SELECT COUNT(*) FROM chat_session")
                overview["sessions"]["session_count"] = int(rows[0][0]) if rows else 0

            if _table_exists(conn, "session_document"):
                rows = _safe_query(
                    conn,
                    "SELECT COUNT(*) FROM session_document WHERE status NOT IN ('READY', 'FAILED')",
                )
                overview["sessions"]["pending_documents"] = int(rows[0][0]) if rows else 0

            if _table_exists(conn, "rag_query_log"):
                total_rows = _safe_query(conn, "SELECT COUNT(*) FROM rag_query_log")
                overview["rag_traces"]["total"] = int(total_rows[0][0]) if total_rows else 0
                h24_rows = _safe_query(
                    conn,
                    "SELECT COUNT(*) FROM rag_query_log WHERE created_at > NOW() - INTERVAL '24 hours'",
                )
                overview["rag_traces"]["last_24h"] = int(h24_rows[0][0]) if h24_rows else 0
                outcome_rows = _safe_query(
                    conn,
                    "SELECT outcome, COUNT(*) FROM rag_query_log GROUP BY outcome ORDER BY COUNT(*) DESC",
                )
                overview["rag_traces"]["by_outcome"] = {
                    str(row[0]): int(row[1]) for row in outcome_rows
                }

    except Exception as exc:
        logger.exception("system overview db check failed")
        overview["services"]["postgresql"] = {
            "status": "down",
            "latency_ms": None,
            "error": str(exc),
        }

    return overview
