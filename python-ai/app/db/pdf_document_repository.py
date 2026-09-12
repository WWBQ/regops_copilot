"""pdf_document 元数据写入。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import psycopg

from app.ingest.disclosure_dates import disclosure_date_for

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"^(?P<code>\d{6})_(?P<year>\d{4})")


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


def upsert_pdf_document(
    conn: psycopg.Connection,
    *,
    doc_id: str,
    pdf_path: Path,
    content_hash: str,
    bucket: str,
    object_key: str,
    page_count: int,
    parse_object_key: str | None = None,
    ingest_status: str = "ready",
) -> None:
    company_code, report_year = infer_company_year(pdf_path)
    file_size = pdf_path.stat().st_size
    disclosure_date = disclosure_date_for(doc_id)
    from app.rag.dept_scope import depts_for_company

    dept_acl = json.dumps(depts_for_company(company_code), ensure_ascii=False)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pdf_document (
                doc_id, company_code, report_year, doc_type, title, source_filename,
                content_type, content_hash, storage_backend, bucket, object_key,
                parse_object_key, file_size_bytes, page_count, version, is_active,
                ingest_status, disclosure_date, source_site, meta, dept_acl
            ) VALUES (
                %s, %s, %s, 'annual_report', %s, %s,
                'application/pdf', %s, 'local', %s, %s,
                %s, %s, %s, 1, TRUE,
                %s, %s, 'cninfo', '{}'::jsonb, %s::jsonb
            )
            ON CONFLICT (doc_id, version) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                object_key = EXCLUDED.object_key,
                parse_object_key = COALESCE(EXCLUDED.parse_object_key, pdf_document.parse_object_key),
                file_size_bytes = EXCLUDED.file_size_bytes,
                page_count = EXCLUDED.page_count,
                ingest_status = EXCLUDED.ingest_status,
                disclosure_date = COALESCE(EXCLUDED.disclosure_date, pdf_document.disclosure_date),
                dept_acl = EXCLUDED.dept_acl,
                updated_at = NOW()
            """,
            (
                doc_id,
                company_code,
                report_year,
                pdf_path.stem,
                pdf_path.name,
                content_hash,
                bucket,
                object_key,
                parse_object_key,
                file_size,
                page_count,
                ingest_status,
                disclosure_date,
                dept_acl,
            ),
        )
    logger.info(
        "upserted pdf_document doc_id=%s pages=%d disclosure_date=%s",
        doc_id,
        page_count,
        disclosure_date,
    )


def backfill_disclosure_dates(conn: psycopg.Connection) -> int:
    """按 DISCLOSURE_DATES 回填已入库行（仅覆盖 disclosure_date 为空或与表不一致的）。"""
    from app.ingest.disclosure_dates import DISCLOSURE_DATES

    updated = 0
    with conn.cursor() as cur:
        for doc_id, day in DISCLOSURE_DATES.items():
            cur.execute(
                """
                UPDATE pdf_document
                SET disclosure_date = %s, updated_at = NOW()
                WHERE doc_id = %s
                  AND (disclosure_date IS DISTINCT FROM %s)
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
            WHERE ingest_status = 'ready' AND is_active = TRUE
            ORDER BY company_code, report_year DESC
            """
        )
        return [row[0] for row in cur.fetchall()]
