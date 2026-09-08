#!/usr/bin/env python3
"""W9-2 金融红队 CLI（fixture，不调 LLM）。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_w9_redteam.py
  python-ai/.venv/bin/python eval/run_w9_redteam.py --fail-on-regression
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.redteam_runner import render_markdown, run_redteam_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W9 financial red-team eval")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w9_redteam_25.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="accuracy 未满或 SQL/越权/数字/密钥泄露率 > 0 则非零退出",
    )
    args = parser.parse_args()

    report = run_redteam_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
    )
    out_dir = args.out or (
        REPORTS_DIR / "w9_redteam" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    summary = report["summary"]
    print(
        json.dumps(
            {
                "n": summary["total"],
                "accuracy": summary["accuracy"],
                "sql_leak_rate": summary["sql_leak_rate"],
                "acl_leak_rate": summary["acl_leak_rate"],
                "number_error_rate": summary["number_error_rate"],
                "secret_leak_rate": summary["secret_leak_rate"],
            },
            ensure_ascii=False,
        )
    )
    print(f"Report: {out_dir / 'report.md'}")
    if args.fail_on_regression:
        leaks = (
            summary["sql_leak_rate"]
            or summary["acl_leak_rate"]
            or summary["number_error_rate"]
            or summary["secret_leak_rate"]
        )
        if summary["accuracy"] < 1 or leaks:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
