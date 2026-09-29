#!/usr/bin/env python3
"""W8-2 三策略 Prompt 对照 CLI（默认 fixture，不调 LLM）。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_w8_strategy.py
  python-ai/.venv/bin/python eval/run_w8_strategy.py --category concept
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
from app.eval.strategy_runner import render_markdown, run_strategy_eval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W8 prompt strategy comparison")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w8_prompt_30.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--category",
        default="",
        choices=["", "concept", "numeric_unbacked", "numeric_trap", "refuse", "format"],
    )
    args = parser.parse_args()

    report = run_strategy_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
        seed=args.seed,
    )
    out_dir = args.out or (REPORTS_DIR / "w8_strategy" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    summary = report["summary"]
    print(json.dumps({k: summary[k] for k in ("n", "backend", "seed") if k in summary}, ensure_ascii=False))
    for name, row in summary["by_strategy"].items():
        print(
            f"  {name}: acc={row['accuracy']:.1%} num_err={row['number_error_rate']:.1%} "
            f"tokens={row['avg_tokens']:.0f} p50={row['latency_p50_ms']:.0f}ms"
        )
    for note in summary.get("when_not_worth") or []:
        print(f"  NOT WORTH {note['strategy']}: {note['when']}")
    print(f"Report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
