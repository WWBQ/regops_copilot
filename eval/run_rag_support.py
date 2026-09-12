#!/usr/bin/env python3
"""引用片段是否撑住答案（20 题）。不和检索 Recall@12 混报。

用法：
  python-ai/.venv/bin/python eval/run_rag_support.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.rag_support_runner import run_rag_support_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG snippet-support golden set")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "rag_support_20.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument("--top-k", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    report = run_rag_support_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
        top_k=args.top_k,
    )
    out_dir = args.out_dir or (REPORTS_DIR / "rag_support" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = report["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
