#!/usr/bin/env python3
"""W4 问数黄金集评测 CLI。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_asknum.py
  python-ai/.venv/bin/python eval/run_asknum.py --category blocked

走 try_answer(persist_trace=False)，不调 LLM；需要 fin_metric 已入库。
--fail-on-regression 时，accuracy < 100% 或出现数字泄露则非零退出。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.asknum_runner import render_markdown, run_asknum_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W4 asknum golden set eval")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w4_asknum_20.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--category",
        default="",
        choices=["", "hit", "blocked", "clarify", "skip", "missing", "compare", "multi"],
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="accuracy 未满或拦截路径泄露金额时以非零码退出",
    )
    args = parser.parse_args()

    report = run_asknum_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
    )

    out_dir = args.out or (REPORTS_DIR / "w4_asknum" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(json.dumps({k: v for k, v in summary.items() if k != "by_category"}, ensure_ascii=False, indent=2))
    for row in report["results"]:
        if not row["passed"]:
            print(
                f"  FAIL {row['id']} 期望 {row['expected_route']} 实际 {row['actual_route']}：{row['detail']}"
            )
    print(f"Report: {out_dir / 'report.json'}")
    print(f"Report: {out_dir / 'report.md'}")

    if args.fail_on_regression and (summary["accuracy"] < 1.0 or summary["leak_count"] > 0):
        print("检测到回归：accuracy < 100% 或存在数字泄露", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
