#!/usr/bin/env python3
"""Smoke test：BGE-M3 本地 embed（首次会下载模型）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest.embeddings import embed_text, get_embedding_model, vector_to_pg_literal


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "公司面临的主要风险包括原材料价格波动。"
    model = get_embedding_model()
    print(f"model={model.model_name} device={model._resolve_device()}")
    vec = embed_text(text, model=model)
    print(f"dim={len(vec)} head={vec[:5]}")
    print(f"pg_literal_len={len(vector_to_pg_literal(vec))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
