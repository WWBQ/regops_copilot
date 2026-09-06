#!/usr/bin/env python3
"""W1 /chat 黄金集评测 CLI（薄封装）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402
from app.eval.w1_chat_runner import run_w1_chat_eval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W1 chat golden set eval")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "w1_chat_30.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--model",
        default="",
        help="发给 /chat 的模型名（deepseek / qwen）；空则用服务 DEFAULT_MODEL",
    )
    args = parser.parse_args()

    report = run_w1_chat_eval(
        golden_path=args.golden,
        base_url=args.base_url,
        limit=args.limit,
        model=args.model or None,
    )
    out_dir = args.out or (REPORTS_DIR / "w1_chat" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report: {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
