"""disclosure_date 映射与 upsert 写入。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from app.db.pdf_document_repository import upsert_pdf_document
from app.ingest.disclosure_dates import DISCLOSURE_DATES, disclosure_date_for


def test_disclosure_date_map_covers_ingested_corpus():
    assert disclosure_date_for("002594_2024") == date(2025, 3, 25)
    assert disclosure_date_for("000651_2024") == date(2025, 4, 28)
    assert disclosure_date_for("unknown_2024") is None
    assert len(DISCLOSURE_DATES) >= 12


def test_upsert_pdf_document_writes_disclosure_date(tmp_path: Path):
    pdf = tmp_path / "002594_2024_annual.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    upsert_pdf_document(
        conn,
        doc_id="002594_2024",
        pdf_path=pdf,
        content_hash="abc",
        bucket="docs",
        object_key="002594_2024.pdf",
        page_count=10,
    )

    args = cur.execute.call_args.args
    sql = args[0]
    params = args[1]
    assert "disclosure_date" in sql
    assert date(2025, 3, 25) in params
