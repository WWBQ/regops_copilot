#!/usr/bin/env python3
"""W8-3 Prompt A/B CLI：固定种子、随机顺序、Wilson / McNemar。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_w8_ab.py
  python-ai/.venv/bin/python eval/run_w8_ab.py --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.ab_runner import render_markdown, run_ab_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W8 prompt A/B eval")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w8_prompt_30.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--write-example",
        action="store_true",
        help="同时写入 eval/prompt_ab/examples/ab_n30_delta3.md",
    )
    args = parser.parse_args()

    report = run_ab_eval(
        golden_path=args.golden,
        limit=args.limit,
        seed=args.seed,
    )
    markdown = render_markdown(report)
    out_dir = args.out or (REPORTS_DIR / "w8_ab" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(markdown, encoding="utf-8")
    if args.write_example:
        example = ROOT / "eval" / "prompt_ab" / "examples" / "ab_n30_delta3.md"
        example.parent.mkdir(parents=True, exist_ok=True)
        example.write_text(markdown, encoding="utf-8")
        print(f"Example: {example}")
    summary = report["summary"]
    print(
        json.dumps(
            {
                "n": summary["n"],
                "accuracy_a": summary["accuracy_a"],
                "accuracy_b": summary["accuracy_b"],
                "delta": summary["delta"],
                "mcnemar_p": summary["mcnemar_p"],
                "credible": summary["credible"],
                "verdict": summary["verdict"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Report: {out_dir / 'report.md'}")
    return 0 if not summary["credible"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
