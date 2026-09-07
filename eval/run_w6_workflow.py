#!/usr/bin/env python3
"""W6-6 审查工作流轨迹黄金集评测 CLI（不调 LLM）。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_w6_workflow.py
  python-ai/.venv/bin/python eval/run_w6_workflow.py --category budget
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402
from app.eval.workflow_runner import render_markdown, run_workflow_eval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W6-6 workflow trajectory golden set")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w6_workflow_20.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--category",
        default="",
        choices=[
            "",
            "happy",
            "fuzzy",
            "tool_fail",
            "hitl",
            "unauthorized",
            "route",
            "injection",
            "fabricate",
            "budget",
        ],
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="accuracy 未满时以非零码退出",
    )
    args = parser.parse_args()

    report = run_workflow_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
    )

    out_dir = args.out or (
        REPORTS_DIR / "w6_workflow" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(json.dumps({k: v for k, v in summary.items() if k not in {"by_category", "fail_by_node"}}, ensure_ascii=False, indent=2))
    for row in report["results"]:
        if not row["passed"]:
            print(f"  FAIL {row['id']}：{row['detail']}")
    print(f"Report: {out_dir / 'report.json'}")
    print(f"Report: {out_dir / 'report.md'}")

    if args.fail_on_regression and summary["accuracy"] < 1.0:
        print("检测到回归：accuracy < 100%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
