"""pdf_document 元数据读写；它是 PDF 文档元数据的唯一来源。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json

from app.ingest.disclosure_dates import disclosure_date_for

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"^(?P<code>\d{6})_(?P<year>\d{4})")


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    bucket: str
    object_key: str
    content_hash: str
    source_filename: str
    content_type: str
    size: int
    created_at: str
    updated_at: str
    parse_object_key: str | None = None
    doc_type: str = "annual_report"
    ingest_status: str = "uploaded"
    meta: dict[str, Any] | None = None


def infer_doc_id(pdf_path: Path) -> str:
    match = _FILENAME_RE.match(pdf_path.stem)
    if match:
        return f"{match.group('code')}_{match.group('year')}"
    return pdf_path.stem


def infer_company_year(pdf_path: Path) -> tuple[str | None, int | None]:
    match = _FILENAME_RE.match(pdf_path.stem)
    if not match:
        return None, None
    return match.group("code"), int(match.group("year"))


def _record(row: tuple[Any, ...] | None) -> DocumentRecord | None:
    if row is None:
        return None
    meta = row[12] if isinstance(row[12], dict) else json.loads(row[12] or "{}")
    return DocumentRecord(
        doc_id=str(row[0]),
        bucket=str(row[1]),
        object_key=str(row[2]),
        content_hash=str(row[3]),
        source_filename=str(row[4]),
        content_type=str(row[5]),
        size=int(row[6]),
        parse_object_key=row[7],
        created_at=row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        updated_at=row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
        doc_type=str(row[10]),
        ingest_status=str(row[11]),
        meta=meta,
    )


_SELECT_FIELDS = """
    doc_id, bucket, object_key, content_hash, source_filename, content_type,
    file_size_bytes, parse_object_key, created_at, updated_at,
    doc_type, ingest_status, meta
"""


def get_pdf_document(conn: psycopg.Connection, doc_id: str) -> DocumentRecord | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_SELECT_FIELDS}
                FROM pdf_document
                WHERE doc_id = %s AND is_active = TRUE
                ORDER BY version DESC
                LIMIT 1""",
            (doc_id,),
        )
        return _record(cur.fetchone())


def list_pdf_documents(
    conn: psycopg.Connection,
    *,
    include_session: bool = False,
) -> list[DocumentRecord]:
    session_filter = "" if include_session else "AND doc_type <> 'session_upload'"
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_SELECT_FIELDS}
                FROM pdf_document
                WHERE is_active = TRUE {session_filter}
                ORDER BY updated_at DESC"""
        )
        return [record for row in cur.fetchall() if (record := _record(row)) is not None]


def upsert_uploaded_pdf_document(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    source_filename: str,
    content_type: str,
    content_hash: str,
    bucket: str,
    object_key: str,
    file_size: int,
    doc_type: str | None = None,
    ingest_status: str = "uploaded",
    parse_object_key: str | None = None,
    page_count: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    path = Path(source_filename)
    # 重解析使用对象存储里的哈希文件名；年报身份以稳定的 doc_id 为准。
    company_code, report_year = infer_company_year(Path(doc_id))
    if company_code is None:
        company_code, report_year = infer_company_year(path)
    resolved_type = doc_type or ("annual_report" if company_code and report_year else "uploaded_pdf")
    disclosure_date = disclosure_date_for(doc_id)
    from app.rag.dept_scope import depts_for_company

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pdf_document (
                doc_id, company_code, report_year, doc_type, title, source_filename,
                content_type, content_hash, storage_backend, bucket, object_key,
                parse_object_key, file_size_bytes, page_count, version, is_active,
                ingest_status, disclosure_date, source_site, meta, dept_acl
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, 'local', %s, %s,
                %s, %s, %s, 1, TRUE,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (doc_id, version) DO UPDATE SET
                company_code = EXCLUDED.company_code,
                report_year = EXCLUDED.report_year,
                doc_type = EXCLUDED.doc_type,
                title = EXCLUDED.title,
                source_filename = EXCLUDED.source_filename,
                content_type = EXCLUDED.content_type,
                content_hash = EXCLUDED.content_hash,
                bucket = EXCLUDED.bucket,
                object_key = EXCLUDED.object_key,
                parse_object_key = CASE
                    WHEN pdf_document.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                        THEN EXCLUDED.parse_object_key
                    ELSE COALESCE(EXCLUDED.parse_object_key, pdf_document.parse_object_key)
                END,
                file_size_bytes = EXCLUDED.file_size_bytes,
                page_count = CASE
                    WHEN pdf_document.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                        THEN EXCLUDED.page_count
                    ELSE COALESCE(EXCLUDED.page_count, pdf_document.page_count)
                END,
                ingest_status = EXCLUDED.ingest_status,
                disclosure_date = COALESCE(EXCLUDED.disclosure_date, pdf_document.disclosure_date),
                source_site = EXCLUDED.source_site,
                meta = EXCLUDED.meta,
                dept_acl = EXCLUDED.dept_acl,
                updated_at = NOW()
            """,
            (
                doc_id,
                company_code,
                report_year,
                resolved_type,
                path.stem,
                source_filename,
                content_type,
                content_hash,
                bucket,
                object_key,
                parse_object_key,
                file_size,
                page_count,
                ingest_status,
                disclosure_date,
                "session" if resolved_type == "session_upload" else "cninfo",
                Json(meta or {}),
                Json(depts_for_company(company_code)),
            ),
        )


def update_pdf_document_ingest(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    ingest_status: str,
    parse_object_key: str | None = None,
    page_count: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pdf_document
            SET ingest_status = %s,
                parse_object_key = COALESCE(%s, parse_object_key),
                page_count = COALESCE(%s, page_count),
                updated_at = NOW()
            WHERE doc_id = %s AND is_active = TRUE
            """,
            (ingest_status, parse_object_key, page_count, doc_id),
        )


def upsert_pdf_document(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    pdf_path: Path,
    source_filename: str,
    content_hash: str,
    bucket: str,
    object_key: str,
    page_count: int,
    parse_object_key: str | None = None,
    ingest_status: str = "ready",
) -> None:
    upsert_uploaded_pdf_document(
        conn,
        doc_id=doc_id,
        source_filename=source_filename,
        content_type="application/pdf",
        content_hash=content_hash,
        bucket=bucket,
        object_key=object_key,
        file_size=pdf_path.stat().st_size,
        doc_type="annual_report",
        ingest_status=ingest_status,
        parse_object_key=parse_object_key,
        page_count=page_count,
    )
    logger.info("upserted pdf_document doc_id=%s pages=%d", doc_id, page_count)


def backfill_disclosure_dates(conn: psycopg.Connection) -> int:
    """按 DISCLOSURE_DATES 回填已入库行。"""
    from app.ingest.disclosure_dates import DISCLOSURE_DATES

    updated = 0
    with conn.cursor() as cur:
        for doc_id, day in DISCLOSURE_DATES.items():
            cur.execute(
                """
                UPDATE pdf_document
                SET disclosure_date = %s, updated_at = NOW()
                WHERE doc_id = %s AND disclosure_date IS DISTINCT FROM %s
                """,
                (day, doc_id, day),
            )
            updated += cur.rowcount
    return updated


def list_company_ready_doc_ids(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id FROM pdf_document
            WHERE ingest_status = 'ready'
              AND is_active = TRUE
              AND company_code IS NOT NULL
              AND doc_type <> 'session_upload'
            ORDER BY company_code, report_year DESC
            """
        )
        return [row[0] for row in cur.fetchall()]
