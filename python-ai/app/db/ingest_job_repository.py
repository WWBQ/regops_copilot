"""ingest_job 状态写入（会话 ingest 与批量 ingest 共用）。"""

from __future__ import annotations

import logging
import uuid

import psycopg

logger = logging.getLogger(__name__)


def create_job(
    conn: psycopg.Connection,
    *,
    target_type: str,
    target_doc_id: str,
    status: str = "PENDING",
) -> str:
    job_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_job (job_id, target_type, target_doc_id, status)
            VALUES (%s::uuid, %s, %s, %s)
            """,
            (job_id, target_type, target_doc_id, status),
        )
    logger.info("created ingest_job job_id=%s doc_id=%s status=%s", job_id, target_doc_id, status)
    return job_id


def get_job(conn: psycopg.Connection, job_id: str) -> tuple | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT job_id::text, target_type, target_doc_id, status,
                   error_message, retry_count, created_at, updated_at, finished_at
            FROM ingest_job
            WHERE job_id = %s::uuid
            """,
            (job_id,),
        )
        return cur.fetchone()


def update_job_status(
    conn: psycopg.Connection,
    *,
    job_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    finished = status in ("DONE", "FAILED")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingest_job
            SET status = %s,
                error_message = %s,
                updated_at = NOW(),
                finished_at = CASE WHEN %s THEN NOW() ELSE finished_at END
            WHERE job_id = %s::uuid
            """,
            (status, error_message, finished, job_id),
        )
