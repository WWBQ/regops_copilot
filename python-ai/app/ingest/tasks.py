"""RabbitMQ/Celery 解析队列；Redis 缓存任务状态，PDF 从共享对象存储读取。"""

from __future__ import annotations

import logging

from celery import Celery

from app.config import get_settings
from app.db.connection import get_connection
from app.db.ingest_job_repository import get_job, update_job_status
from app.db.session_repository import update_document_status
from app.ingest.pipeline import _build_document_service, ingest_pdf_to_vectors
from app.ingest.session_pipeline import ingest_session_pdf

logger = logging.getLogger(__name__)

celery_app = Celery(
    "regops_ingest",
    broker=get_settings().ingest_broker_url,
    backend=get_settings().ingest_result_backend,
)
celery_app.conf.update(
    task_default_queue="ingest",
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=False,
    result_expires=86400,
    task_track_started=True,
    task_default_delivery_mode="persistent",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # RabbitMQ 4.3+ 禁止 transient non-exclusive 队列；Celery 5.6 控制/事件队列默认非独占。
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    task_publish_retry=True,
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 1, "interval_max": 2},
)


def enqueue_batch(batch_id: str) -> None:
    process_ingest_batch.apply_async(args=[batch_id], task_id=batch_id, queue="ingest")


def enqueue_session_document(session_id: str, doc_id: str, job_id: str, filename: str) -> None:
    process_session_document.apply_async(
        args=[session_id, doc_id, job_id, filename], task_id=job_id, queue="ingest"
    )


def _fail_job(job_id: str, error: Exception) -> None:
    with get_connection() as conn:
        row = get_job(conn, job_id)
        if row and row[3] != "FAILED":
            update_job_status(conn, job_id=job_id, status="FAILED", error_message=str(error)[:2000])
            conn.commit()


@celery_app.task(name="regops.ingest_batch")
def process_ingest_batch(batch_id: str) -> None:
    """一个队列消息对应一个批次；重投递时跳过已完成/失败的文件。"""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.job_id::text, j.target_doc_id, j.status,
                       b.use_parse_cache, b.parser_backend
                FROM ingest_job j JOIN ingest_batch b ON b.batch_id = j.batch_id
                WHERE b.batch_id = %s::uuid
                ORDER BY j.created_at, j.id
                """,
                (batch_id,),
            )
            jobs = cur.fetchall()
    if not jobs:
        logger.error("ingest batch has no files batch_id=%s", batch_id)
        return

    service = _build_document_service()
    for job_id, doc_id, status, use_parse_cache, parser_backend in jobs:
        if status in ("DONE", "FAILED"):
            continue
        try:
            ingest_pdf_to_vectors(
                service.local_pdf_path(doc_id),
                doc_id=doc_id,
                job_id=job_id,
                use_parse_cache=use_parse_cache,
                parser_backend=parser_backend,
            )
        except Exception as exc:
            logger.exception("ingest batch file failed batch_id=%s doc_id=%s", batch_id, doc_id)
            _fail_job(job_id, exc)


@celery_app.task(name="regops.ingest_session_document")
def process_session_document(session_id: str, doc_id: str, job_id: str, filename: str) -> None:
    """会话 PDF 也经队列执行，避免 API 进程重启时丢失后台任务。"""

    with get_connection() as conn:
        row = get_job(conn, job_id)
    if row is None or row[3] in ("DONE", "FAILED"):
        return
    try:
        body = _build_document_service().local_pdf_path(doc_id).read_bytes()
        ingest_session_pdf(
            session_id=session_id, job_id=job_id, body=body, source_filename=filename,
        )
    except Exception as exc:
        logger.exception("session ingest failed session_id=%s doc_id=%s", session_id, doc_id)
        with get_connection() as conn:
            update_job_status(conn, job_id=job_id, status="FAILED", error_message=str(exc)[:2000])
            update_document_status(
                conn, session_id=session_id, doc_id=doc_id, status="FAILED",
                error_message=str(exc)[:2000],
            )
            conn.commit()
