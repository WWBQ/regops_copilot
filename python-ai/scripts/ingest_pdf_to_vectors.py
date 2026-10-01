#!/usr/bin/env python3
"""批量 ingest：data/raw 下 PDF → chunk → BGE-M3 → doc_chunks。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import ROOT_DIR, get_settings
from app.db.connection import get_connection
from app.db.pdf_document_repository import infer_doc_id
from app.ingest.pipeline import ingest_pdf_to_vectors
from app.ingest.parser import SUPPORTED_PARSER_BACKENDS
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)
RAW_DIR = ROOT_DIR / "data" / "raw"


def _check_db() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute(
                "SELECT to_regclass('public.doc_chunks'), to_regclass('public.pdf_document')"
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise SystemExit(
                    "doc_chunks 表不存在。请先: docker compose up -d db && "
                    "psql ... -f docs/sql/w2_tables.sql"
                )


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Ingest PDFs into pgvector doc_chunks")
    parser.add_argument("pdfs", nargs="*", help="PDF paths; default all in data/raw")
    parser.add_argument("--no-parse-cache", action="store_true", help="force re-parse")
    parser.add_argument(
        "--parser",
        choices=SUPPORTED_PARSER_BACKENDS,
        help="PDF parser; default reads DOCUMENT_PARSER_BACKEND",
    )
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--chunk-overlap", type=int, default=128)
    args = parser.parse_args()

    _check_db()
    settings = get_settings()
    logger.info(
        "database=%s embedding=%s parser=%s",
        settings.database_url.split("@")[-1],
        settings.embedding_model,
        args.parser or settings.document_parser_backend,
    )

    paths = [Path(p).expanduser() for p in args.pdfs] if args.pdfs else sorted(RAW_DIR.glob("*.pdf"))
    if not paths:
        logger.error("no PDFs found under %s", RAW_DIR)
        return 1

    ok = 0
    for pdf_path in paths:
        if not pdf_path.is_absolute():
            pdf_path = (Path.cwd() / pdf_path).resolve()
        doc_id = infer_doc_id(pdf_path)
        logger.info("=== start %s doc_id=%s ===", pdf_path.name, doc_id)
        try:
            result = ingest_pdf_to_vectors(
                pdf_path,
                doc_id=doc_id,
                use_parse_cache=not args.no_parse_cache,
                parser_backend=args.parser,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            print(
                f"OK {result.doc_id}: pages={result.pages} chunks={result.chunks} "
                f"parser={result.parser_backend} parse_cached={result.parse_cached} "
                f"job_id={result.job_id}"
            )
            ok += 1
        except Exception:
            logger.exception("failed doc_id=%s", doc_id)
            print(f"FAIL {doc_id}", file=sys.stderr)

    print(f"done {ok}/{len(paths)}")
    return 0 if ok == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
