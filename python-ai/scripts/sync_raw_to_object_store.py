#!/usr/bin/env python3
"""把 data/raw 里的 PDF 同步到本地 ObjectStore（COS 模拟层）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.documents.registry import DocumentRegistry
from app.documents.service import DocumentService
from app.storage.local import LocalObjectStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload local PDFs into LocalObjectStore")
    parser.add_argument("paths", nargs="*", help="PDF paths; default: all PDFs in data/raw")
    parser.add_argument("--doc-id", help="Override doc_id for single-file upload")
    args = parser.parse_args()

    settings = get_settings()
    store = LocalObjectStore(
        Path(settings.object_store_root),
        default_bucket=settings.object_store_bucket,
        public_base_url=settings.api_public_base_url,
        presign_secret=settings.object_store_presign_secret,
    )
    registry = DocumentRegistry(Path(settings.object_store_root) / "_registry" / "documents.json")
    service = DocumentService(store, registry, default_bucket=settings.object_store_bucket)

    raw_dir = ROOT.parent / "data" / "raw"
    paths = [Path(p) for p in args.paths] if args.paths else sorted(raw_dir.glob("*.pdf"))
    if not paths:
        print(f"no PDFs found under {raw_dir}")
        return 1

    for path in paths:
        body = path.read_bytes()
        doc_id = args.doc_id if len(paths) == 1 and args.doc_id else None
        result = service.upload_pdf(body, path.name, doc_id=doc_id)
        flag = "reused" if result.reused else "uploaded"
        print(f"[{flag}] doc_id={result.doc_id} key={result.object_key} size={result.size}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
