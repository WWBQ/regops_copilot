#!/usr/bin/env python3
"""回填 pdf_document.disclosure_date（巨潮公告日）。

用法（项目根或 python-ai）：
  python-ai/.venv/bin/python python-ai/scripts/backfill_disclosure_dates.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-ai"))

from app.db.connection import get_connection  # noqa: E402
from app.db.pdf_document_repository import backfill_disclosure_dates  # noqa: E402
from app.ingest.disclosure_dates import DISCLOSURE_DATES  # noqa: E402


def main() -> int:
    with get_connection() as conn:
        updated = backfill_disclosure_dates(conn)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, report_year, disclosure_date
                FROM pdf_document
                WHERE is_active = TRUE
                ORDER BY company_code, report_year
                """
            )
            rows = cur.fetchall()
    print(f"updated={updated} known_map={len(DISCLOSURE_DATES)}")
    for doc_id, year, day in rows:
        print(f"  {doc_id} report_year={year} disclosure_date={day}")
    missing = [doc_id for doc_id, _, day in rows if day is None]
    if missing:
        print(f"still_null={missing}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
