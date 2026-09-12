#!/usr/bin/env python3
"""W3-5 RAG 检索消融 CLI：同一黄金集跑 baseline / hybrid / rerank。

用法（项目根目录）：
  python-ai/.venv/bin/python eval/run_rag_ablation.py
  python-ai/.venv/bin/python eval/run_rag_ablation.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-ai"))

from app.eval.rag_ablation import render_markdown, run_rag_ablation_eval  # noqa: E402
from app.eval.registry import GOLDEN_DIR, REPORTS_DIR  # noqa: E402
from app.rag.modes import ABLATION_MODES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG retrieval ablation (baseline/hybrid/rerank)")
    parser.add_argument("--golden", type=Path, default=GOLDEN_DIR / "rag_retrieval_100.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", type=str, default="")
    parser.add_argument("--top-k", type=int, default=0)
    parser.add_argument("--label", type=str, default="ablation")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    def on_progress(mode: str, done: int, total: int, item_id: str) -> None:
        print(f"[{mode}] {done}/{total} {item_id}", flush=True)

    report = run_rag_ablation_eval(
        golden_path=args.golden,
        limit=args.limit,
        category=args.category,
        top_k=args.top_k,
        label=args.label,
        on_progress=on_progress,
    )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (REPORTS_DIR / "rag_ablation" / f"{ts}_{args.label.strip() or 'ablation'}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown = render_markdown(report)
    (out_dir / "report.md").write_text(markdown, encoding="utf-8")
    for mode in ABLATION_MODES:
        mode_dir = out_dir / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        (mode_dir / "report.json").write_text(
            json.dumps(report["reports"][mode], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    by_mode = report["summary"]["by_mode"]
    print(json.dumps({mode: by_mode[mode] for mode in ABLATION_MODES}, ensure_ascii=False, indent=2))
    for pair in report["summary"]["adjacent"]:
        print(
            f"{pair['from']} → {pair['to']}: recall Δ {pair['recall_at_k_delta']:+.4f} "
            f"mrr Δ {pair['mrr_delta']:+.4f} cite Δ {pair.get('citation_accuracy_delta', 0):+.4f} "
            f"p50 Δ {pair['latency_p50_ms_delta']:+.0f}ms "
            f"up={len(pair['improvements'])} down={len(pair['regressions'])}"
        )
    print(f"Report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
