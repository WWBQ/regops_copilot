#!/usr/bin/env python3
"""校验 RAG 检索黄金集，并把可审计报告写入 eval/reports。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.golden_validation import validate_rag_retrieval_golden  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the RAG retrieval golden set")
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "eval" / "golden" / "rag_retrieval_100.json",
    )
    parser.add_argument("--skip-corpus", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    report = validate_rag_retrieval_golden(
        args.golden,
        check_corpus=not args.skip_corpus,
    )
    out_dir = args.out_dir or (
        ROOT / "eval" / "reports" / "rag_golden_validation" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "item_count", "error_count", "warning_count")}, ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
