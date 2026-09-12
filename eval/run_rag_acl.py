#!/usr/bin/env python3
"""检索层部门 ACL 评测 CLI（不调 LLM）。

用法：
  python-ai/.venv/bin/python eval/run_rag_acl.py
  python-ai/.venv/bin/python eval/run_rag_acl.py --fail-on-regression
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.rag_guard_runner import render_markdown, run_rag_guard_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG department ACL golden set")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "rag_acl_20.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    report = run_rag_guard_eval(
        golden_path=args.golden,
        task_id="rag_acl",
        limit=args.limit,
        category=args.category,
    )
    out_dir = args.out or (REPORTS_DIR / "rag_acl" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    summary = report["summary"]
    print(json.dumps(
        {k: summary[k] for k in ("total", "accuracy", "false_accept_rate", "leak_rate")},
        ensure_ascii=False,
    ))
    print(f"Report: {out_dir / 'report.md'}")
    if args.fail_on_regression and (summary["accuracy"] < 1 or summary["leak_rate"] or summary["false_accept_rate"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
