#!/usr/bin/env python3
"""扫描普通/比较 RAG 的重排候选数，输出质量与延迟报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.golden_validation import validate_rag_retrieval_golden  # noqa: E402
from app.eval.rag_tuning import run_rag_tuning  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune RAG rerank candidate limits")
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "eval" / "golden" / "rag_retrieval_100.json",
    )
    parser.add_argument("--candidates", default="12,24,40,80")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--items-per-category",
        type=int,
        default=2,
        help="默认每个题型分层抽样 2 题；传 0 且 --limit=0 才跑全部 100 题",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--profile",
        choices=("all", "standard", "comparison"),
        default="all",
    )
    args = parser.parse_args()

    validation = validate_rag_retrieval_golden(args.golden, check_corpus=True)
    if validation["status"] != "passed":
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        print("黄金集校验未通过，停止寻优，避免用错误尺子选参数。", file=sys.stderr)
        return 2

    candidates = [int(value.strip()) for value in args.candidates.split(",") if value.strip()]

    def on_progress(profile: str, done: int, total: int, item_id: str) -> None:
        print(f"[{profile}] {done}/{total} {item_id}", flush=True)

    report = run_rag_tuning(
        golden_path=args.golden,
        candidates=candidates,
        limit=args.limit,
        items_per_category=args.items_per_category,
        profile=args.profile,
        on_progress=on_progress,
    )
    report["golden_validation"] = validation
    out_dir = args.out_dir or (
        ROOT / "eval" / "reports" / "rag_tuning" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["recommendation"], ensure_ascii=False, indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
