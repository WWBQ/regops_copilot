#!/usr/bin/env python3
"""合规结论 Schema 校验黄金集评测 CLI（薄封装）。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_compliance_schema.py
  python-ai/.venv/bin/python eval/run_compliance_schema.py --category invalid

不依赖服务在线：纯 Pydantic 校验，可直接当回归门禁。
--fail-on-regression 时，只要出现误放行/误拒/理由错配就返回非零退出码。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.compliance_schema_runner import (  # noqa: E402
    render_markdown,
    run_compliance_schema_eval,
)
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ComplianceConclusion schema golden set eval")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "compliance_schema_20.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="", choices=["", "valid", "invalid"])
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="存在误放行 / 误拒 / 报错理由错配时以非零码退出（CI 门禁用）",
    )
    args = parser.parse_args()

    report = run_compliance_schema_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
    )

    out_dir = args.out or (
        REPORTS_DIR / "compliance_schema" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(json.dumps({k: v for k, v in summary.items() if k != "by_rule"}, ensure_ascii=False, indent=2))
    for row in report["results"]:
        if not row["passed"]:
            print(f"  FAIL {row['id']} [{row['rule']}] 期望 {row['expected']} 实际 {row['actual']}：{row['detail']}")
    print(f"Report: {out_dir / 'report.json'}")
    print(f"Report: {out_dir / 'report.md'}")

    if args.fail_on_regression and summary["strict_pass_rate"] < 1.0:
        print("检测到回归：strict_pass_rate < 100%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
