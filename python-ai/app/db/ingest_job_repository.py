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
    batch_id: str | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_job (job_id, target_type, target_doc_id, status, batch_id)
            VALUES (%s::uuid, %s, %s, %s, %s::uuid)
            """,
            (job_id, target_type, target_doc_id, status, batch_id),
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
            RETURNING batch_id::text
            """,
            (status, error_message, finished, job_id),
        )
        row = cur.fetchone()
    if row and row[0]:
        record_batch_snapshot(conn, batch_id=row[0], stage=status, job_id=job_id)


def create_batch(
    conn: psycopg.Connection,
    *,
    doc_ids: list[str],
    title: str,
    parser_backend: str,
    use_parse_cache: bool,
) -> tuple[str, list[str]]:
    """一次解析请求对应一个批次；每个文件仍有独立 ingest_job 阶段。"""

    if not doc_ids or len(doc_ids) != len(set(doc_ids)):
        raise ValueError("batch must contain unique documents")
    batch_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_batch
                (batch_id, title, parser_backend, use_parse_cache, total_files)
            VALUES (%s::uuid, %s, %s, %s, %s)
            """,
            (batch_id, title[:160], parser_backend, use_parse_cache, len(doc_ids)),
        )
    job_ids = [
        create_job(
            conn, target_type="pdf", target_doc_id=doc_id,
            batch_id=batch_id,
        )
        for doc_id in doc_ids
    ]
    record_batch_snapshot(conn, batch_id=batch_id, stage="QUEUED")
    return batch_id, job_ids


def batch_status(*, total: int, active: int, done: int, failed: int) -> str:
    """批次状态由文件状态确定；避免 worker 与 API 各自维护一套状态。"""

    if done + failed >= total:
        if failed == 0:
            return "DONE"
        return "FAILED" if done == 0 else "PARTIAL"
    if active or done or failed:
        return "RUNNING"
    return "QUEUED"


def retry_failed_batch(conn: psycopg.Connection, *, batch_id: str) -> int:
    """只重试终态批次中的失败文件；保留旧事件以便追查。"""

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM ingest_batch WHERE batch_id = %s::uuid FOR UPDATE",
            (batch_id,),
        )
        row = cur.fetchone()
        if row is None or row[0] not in ("FAILED", "PARTIAL"):
            raise ValueError("only failed or partial batches can be retried")
        cur.execute(
            """
            UPDATE ingest_job
            SET status = 'PENDING', error_message = NULL, finished_at = NULL,
                updated_at = NOW(), retry_count = retry_count + 1
            WHERE batch_id = %s::uuid AND status = 'FAILED'
            RETURNING job_id
            """,
            (batch_id,),
        )
        retry_count = len(cur.fetchall())
        if not retry_count:
            raise ValueError("batch has no failed files")
        cur.execute(
            "UPDATE ingest_batch SET started_at = NULL, finished_at = NULL WHERE batch_id = %s::uuid",
            (batch_id,),
        )
    record_batch_snapshot(conn, batch_id=batch_id, stage="RETRY")
    return retry_count


def record_batch_snapshot(
    conn: psycopg.Connection,
    *,
    batch_id: str,
    stage: str,
    job_id: str | None = None,
) -> None:
    """在同一数据库事务中记录任务状态和折线图快照。"""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)::int,
                   COUNT(*) FILTER (WHERE status = 'PENDING')::int,
                   COUNT(*) FILTER (WHERE status NOT IN ('PENDING', 'DONE', 'FAILED'))::int,
                   COUNT(*) FILTER (WHERE status = 'DONE')::int,
                   COUNT(*) FILTER (WHERE status = 'FAILED')::int
            FROM ingest_job WHERE batch_id = %s::uuid
            """,
            (batch_id,),
        )
        total, pending, active, done, failed = cur.fetchone()
        status = batch_status(total=total, active=active, done=done, failed=failed)
        cur.execute(
            """
            UPDATE ingest_batch
            SET status = %s, updated_at = NOW(),
                started_at = CASE WHEN %s <> 'QUEUED'
                                  THEN COALESCE(started_at, NOW()) ELSE started_at END,
                finished_at = CASE WHEN %s IN ('DONE', 'PARTIAL', 'FAILED')
                                   THEN NOW() ELSE NULL END
            WHERE batch_id = %s::uuid
            """,
            (status, status, status, batch_id),
        )
        cur.execute(
            """
            INSERT INTO ingest_batch_event
                (batch_id, job_id, stage, pending_count, active_count, done_count, failed_count)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s)
            """,
            (batch_id, job_id, stage, pending, active, done, failed),
        )
