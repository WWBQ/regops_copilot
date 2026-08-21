"""chat_session / session_document 读写。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

logger = logging.getLogger(__name__)

SESSION_TTL_HOURS = 72


@dataclass(frozen=True)
class SessionDocumentRow:
    doc_id: str
    source_filename: str
    job_id: str | None
    status: str
    page_count: int | None
    chunk_count: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


def create_session(conn: psycopg.Connection, *, title: str | None = None) -> str:
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_session (session_id, title, expires_at)
            VALUES (%s::uuid, %s, %s)
            """,
            (session_id, title, expires_at),
        )
    logger.info("created chat_session session_id=%s", session_id)
    return session_id


def session_exists(conn: psycopg.Connection, session_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM chat_session WHERE session_id = %s::uuid",
            (session_id,),
        )
        return cur.fetchone() is not None


def attach_document(
    conn: psycopg.Connection,
    *,
    session_id: str,
    doc_id: str,
    source_filename: str,
    job_id: str,
    status: str = "PENDING",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO session_document (
                session_id, doc_id, source_filename, job_id, status
            )
            VALUES (%s::uuid, %s, %s, %s::uuid, %s)
            ON CONFLICT (session_id, doc_id) DO UPDATE SET
                source_filename = EXCLUDED.source_filename,
                job_id = EXCLUDED.job_id,
                status = EXCLUDED.status,
                error_message = NULL,
                page_count = NULL,
                chunk_count = NULL,
                updated_at = NOW()
            """,
            (session_id, doc_id, source_filename, job_id, status),
        )


def update_document_status(
    conn: psycopg.Connection,
    *,
    session_id: str,
    doc_id: str,
    status: str,
    page_count: int | None = None,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE session_document
            SET status = %s,
                page_count = COALESCE(%s, page_count),
                chunk_count = COALESCE(%s, chunk_count),
                error_message = %s,
                updated_at = NOW()
            WHERE session_id = %s::uuid AND doc_id = %s
            """,
            (status, page_count, chunk_count, error_message, session_id, doc_id),
        )


def list_session_documents(conn: psycopg.Connection, session_id: str) -> list[SessionDocumentRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, source_filename, job_id::text, status,
                   page_count, chunk_count, error_message, created_at, updated_at
            FROM session_document
            WHERE session_id = %s::uuid
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    return [
        SessionDocumentRow(
            doc_id=row[0],
            source_filename=row[1],
            job_id=row[2],
            status=row[3],
            page_count=row[4],
            chunk_count=row[5],
            error_message=row[6],
            created_at=row[7],
            updated_at=row[8],
        )
        for row in rows
    ]


def get_ready_doc_ids(conn: psycopg.Connection, session_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id FROM session_document
            WHERE session_id = %s::uuid AND status = 'READY'
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        return [row[0] for row in cur.fetchall()]


def get_document_row(
    conn: psycopg.Connection,
    *,
    session_id: str,
    doc_id: str,
) -> SessionDocumentRow | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, source_filename, job_id::text, status,
                   page_count, chunk_count, error_message, created_at, updated_at
            FROM session_document
            WHERE session_id = %s::uuid AND doc_id = %s
            """,
            (session_id, doc_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return SessionDocumentRow(
        doc_id=row[0],
        source_filename=row[1],
        job_id=row[2],
        status=row[3],
        page_count=row[4],
        chunk_count=row[5],
        error_message=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


def row_to_dict(row: SessionDocumentRow) -> dict[str, Any]:
    return {
        "doc_id": row.doc_id,
        "source_filename": row.source_filename,
        "job_id": row.job_id,
        "status": row.status,
        "page_count": row.page_count,
        "chunk_count": row.chunk_count,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }
