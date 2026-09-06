#!/usr/bin/env python3
"""RAG 检索评测 CLI（薄封装）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.rag_retrieval_runner import run_rag_retrieval_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG retrieval golden set eval")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "rag_retrieval_100.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", type=str, default="")
    parser.add_argument("--top-k", type=int, default=0)
    parser.add_argument("--label", type=str, default="", help="可读标签，写入 report.provenance.label")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    report = run_rag_retrieval_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
        top_k=args.top_k,
        label=args.label,
    )
    label_slug = args.label.strip().replace(" ", "-") if args.label.strip() else None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (REPORTS_DIR / "rag_retrieval" / (f"{ts}_{label_slug}" if label_slug else ts))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report: {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
