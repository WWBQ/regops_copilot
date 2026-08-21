"""解析 + 保存整份 JSON artifact。"""

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
from app.ingest.parser import parse_pdf
from app.storage.local import LocalObjectStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse PDF and save full parse JSON artifact")
    parser.add_argument("pdf", nargs="?", help="PDF path; default: uploaded doc via --doc-id")
    parser.add_argument("--doc-id", help="Use uploaded document from ObjectStore")
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

    if args.doc_id:
        pdf_path = service.local_pdf_path(args.doc_id)
        doc_id = args.doc_id
    else:
        pdf_path = Path(args.pdf or "").expanduser()
        if not pdf_path.is_file():
            print("PDF not found; pass path or --doc-id")
            return 1
        body = pdf_path.read_bytes()
        doc_id = service.infer_doc_id(pdf_path.name)
        service.upload_pdf(body, pdf_path.name, doc_id=doc_id)

    blocks = parse_pdf(pdf_path)
    key = service.save_parse_artifact(doc_id, blocks)
    print(f"doc_id={doc_id} pages={len(blocks)} parse_object_key={key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
