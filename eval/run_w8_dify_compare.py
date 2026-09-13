#!/usr/bin/env python3
"""W8-4 Dify 对照 CLI。Dify 没起来或没配 Key 时跳过（退出码 0）。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_w8_dify_compare.py
  DIFY_APP_KEY=app-xxx python-ai/.venv/bin/python eval/run_w8_dify_compare.py --write-example
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.dify_compare import render_markdown, run_dify_compare  # noqa: E402
from app.eval.registry import GOLDEN_DIR  # noqa: E402

EXAMPLE_DIR = ROOT / "eval" / "dify" / "examples"
RUNS_DIR = ROOT / "eval" / "dify" / "runs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Dify chat-messages with /chat")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w8_dify_12.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--write-example", action="store_true")
    args = parser.parse_args()

    report = run_dify_compare(golden_path=args.golden, limit=args.limit, timeout=args.timeout)
    markdown = render_markdown(report)
    out_dir = args.out or (RUNS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "report.md").write_text(markdown, encoding="utf-8")
    if args.write_example:
        EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        (EXAMPLE_DIR / "last_compare.md").write_text(markdown, encoding="utf-8")
        print(f"Example: {EXAMPLE_DIR / 'last_compare.md'}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
