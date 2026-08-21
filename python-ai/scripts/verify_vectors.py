#!/usr/bin/env python3
"""查看 doc_chunks / pdf_document 入库情况。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.connection import get_connection


def main() -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, COUNT(*) AS chunks, COUNT(embedding) AS with_vec
                FROM doc_chunks
                GROUP BY doc_id
                ORDER BY doc_id
                """
            )
            print("=== doc_chunks ===")
            for row in cur.fetchall():
                print(f"  {row[0]}: chunks={row[1]} vectors={row[2]}")

            cur.execute(
                """
                SELECT doc_id, page_count, ingest_status, source_filename
                FROM pdf_document
                ORDER BY doc_id
                """
            )
            print("=== pdf_document ===")
            for row in cur.fetchall():
                print(f"  {row[0]}: pages={row[1]} status={row[2]} file={row[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
