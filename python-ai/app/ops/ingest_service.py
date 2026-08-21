"""解析 / 入库监控数据。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.connection import get_connection


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
        return cur.fetchone()[0] is not None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def fetch_ingest_overview() -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    overview: dict[str, Any] = {
        "checked_at": checked_at,
        "corpus": {
            "documents": [],
            "by_status": {},
            "total_pages": 0,
            "total_chunks": 0,
            "with_parse_artifact": 0,
        },
        "jobs": {
            "by_status": {},
            "total": 0,
            "failed_24h": 0,
            "pending": 0,
        },
        "session_uploads": {
            "by_status": {},
            "total": 0,
            "pending": 0,
        },
    }

    with get_connection() as conn:
        if _table_exists(conn, "pdf_document"):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.doc_id, p.company_code, p.report_year, p.source_filename,
                           p.page_count, p.file_size_bytes, p.content_hash,
                           p.ingest_status, p.parse_object_key IS NOT NULL AS has_parse,
                           p.updated_at,
                           COALESCE(c.chunk_count, 0) AS chunk_count
                    FROM pdf_document p
                    LEFT JOIN (
                        SELECT doc_id, COUNT(*) AS chunk_count
                        FROM doc_chunks
                        GROUP BY doc_id
                    ) c ON c.doc_id = p.doc_id
                    WHERE p.is_active = TRUE
                    ORDER BY p.company_code, p.report_year DESC
                    """
                )
                documents = []
                by_status: dict[str, int] = {}
                total_pages = 0
                total_chunks = 0
                with_parse = 0
                for row in cur.fetchall():
                    status = row[7]
                    by_status[status] = by_status.get(status, 0) + 1
                    pages = int(row[4] or 0)
                    chunks = int(row[10] or 0)
                    total_pages += pages
                    total_chunks += chunks
                    if row[8]:
                        with_parse += 1
                    documents.append(
                        {
                            "doc_id": row[0],
                            "company_code": row[1],
                            "report_year": row[2],
                            "source_filename": row[3],
                            "page_count": pages,
                            "file_size_bytes": int(row[5] or 0),
                            "content_hash": row[6],
                            "ingest_status": status,
                            "has_parse_artifact": bool(row[8]),
                            "chunk_count": chunks,
                            "updated_at": _iso(row[9]),
                        }
                    )
                overview["corpus"]["documents"] = documents
                overview["corpus"]["by_status"] = by_status
                overview["corpus"]["total_pages"] = total_pages
                overview["corpus"]["total_chunks"] = total_chunks
                overview["corpus"]["with_parse_artifact"] = with_parse

        if _table_exists(conn, "ingest_job"):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*)
                    FROM ingest_job
                    GROUP BY status
                    ORDER BY COUNT(*) DESC
                    """
                )
                by_status = {str(row[0]): int(row[1]) for row in cur.fetchall()}
                cur.execute("SELECT COUNT(*) FROM ingest_job")
                total = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT COUNT(*) FROM ingest_job
                    WHERE status = 'FAILED'
                      AND updated_at > NOW() - INTERVAL '24 hours'
                    """
                )
                failed_24h = int(cur.fetchone()[0])
                pending = sum(
                    count
                    for status, count in by_status.items()
                    if status not in ("DONE", "FAILED")
                )
                overview["jobs"]["by_status"] = by_status
                overview["jobs"]["total"] = total
                overview["jobs"]["failed_24h"] = failed_24h
                overview["jobs"]["pending"] = pending

        if _table_exists(conn, "session_document"):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*)
                    FROM session_document
                    GROUP BY status
                    ORDER BY COUNT(*) DESC
                    """
                )
                by_status = {str(row[0]): int(row[1]) for row in cur.fetchall()}
                cur.execute("SELECT COUNT(*) FROM session_document")
                total = int(cur.fetchone()[0])
                pending = sum(
                    count
                    for status, count in by_status.items()
                    if status not in ("READY", "FAILED")
                )
                overview["session_uploads"]["by_status"] = by_status
                overview["session_uploads"]["total"] = total
                overview["session_uploads"]["pending"] = pending

    return overview


def list_ingest_jobs(
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    target_type: str | None = None,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    if target_type:
        clauses.append("target_type = %s")
        params.append(target_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        if not _table_exists(conn, "ingest_job"):
            return {"total": 0, "limit": limit, "offset": offset, "items": []}

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM ingest_job {where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"""
                SELECT job_id::text, target_type, target_doc_id, status,
                       error_message, retry_count, created_at, updated_at, finished_at
                FROM ingest_job
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            items = [
                {
                    "job_id": row[0],
                    "target_type": row[1],
                    "target_doc_id": row[2],
                    "status": row[3],
                    "error_message": row[4],
                    "retry_count": int(row[5] or 0),
                    "created_at": _iso(row[6]),
                    "updated_at": _iso(row[7]),
                    "finished_at": _iso(row[8]),
                }
                for row in cur.fetchall()
            ]

    return {"total": total, "limit": limit, "offset": offset, "items": items}


def list_session_ingest_documents(
    *,
    limit: int = 30,
    offset: int = 0,
    status: str | None = None,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        if not _table_exists(conn, "session_document"):
            return {"total": 0, "limit": limit, "offset": offset, "items": []}

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM session_document {where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"""
                SELECT session_id::text, doc_id, source_filename, job_id::text,
                       status, page_count, chunk_count, error_message,
                       created_at, updated_at
                FROM session_document
                {where}
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            items = [
                {
                    "session_id": row[0],
                    "doc_id": row[1],
                    "source_filename": row[2],
                    "job_id": row[3],
                    "status": row[4],
                    "page_count": row[5],
                    "chunk_count": row[6],
                    "error_message": row[7],
                    "created_at": _iso(row[8]),
                    "updated_at": _iso(row[9]),
                }
                for row in cur.fetchall()
            ]

    return {"total": total, "limit": limit, "offset": offset, "items": items}
