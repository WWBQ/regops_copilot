#!/usr/bin/env python3
"""对比两次 RAG 检索评测 report.json（整体指标 + 逐题回归/提升）。

用法：
  python eval/scripts/compare_rag_reports.py eval/baselines/rag_retrieval/report.json \\
      eval/reports/rag_retrieval/20260821_174606_a4a7b5/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_provenance(report: dict) -> str:
    prov = report.get("provenance") or {}
    git = prov.get("git") or {}
    parts = [
        prov.get("label") or report.get("generated_at", "?"),
        git.get("describe") or git.get("commit", "?")[:8],
    ]
    golden = prov.get("golden") or {}
    if golden.get("sha256"):
        parts.append(f"golden={golden['sha256'][:8]}")
    return " | ".join(str(p) for p in parts if p)


def compare_reports(baseline: dict, candidate: dict) -> dict:
    base_map = {row["id"]: row for row in baseline.get("results") or []}
    cand_map = {row["id"]: row for row in candidate.get("results") or []}
    ids = sorted(set(base_map) | set(cand_map))

    regressions: list[dict] = []
    improvements: list[dict] = []
    rank_changes: list[dict] = []

    for item_id in ids:
        b = base_map.get(item_id)
        c = cand_map.get(item_id)
        if b is None or c is None:
            continue
        b_hit = bool(b.get("page_hit_at_k"))
        c_hit = bool(c.get("page_hit_at_k"))
        if b_hit and not c_hit:
            regressions.append(
                {
                    "id": item_id,
                    "question": c.get("question"),
                    "gold_pages": c.get("gold_pages"),
                    "baseline_pages": b.get("retrieved_pages"),
                    "candidate_pages": c.get("retrieved_pages"),
                }
            )
        elif not b_hit and c_hit:
            improvements.append(
                {
                    "id": item_id,
                    "question": c.get("question"),
                    "gold_pages": c.get("gold_pages"),
                    "baseline_pages": b.get("retrieved_pages"),
                    "candidate_pages": c.get("retrieved_pages"),
                }
            )
        b_rr = float(b.get("reciprocal_rank") or 0)
        c_rr = float(c.get("reciprocal_rank") or 0)
        if abs(b_rr - c_rr) >= 0.01:
            rank_changes.append(
                {
                    "id": item_id,
                    "baseline_mrr": b_rr,
                    "candidate_mrr": c_rr,
                    "delta_mrr": round(c_rr - b_rr, 4),
                }
            )

    base_sum = baseline.get("summary") or {}
    cand_sum = candidate.get("summary") or {}

    category_delta: dict[str, dict] = {}
    for cat in sorted(set(base_sum.get("by_category", {})) | set(cand_sum.get("by_category", {}))):
        b_cat = (base_sum.get("by_category") or {}).get(cat) or {}
        c_cat = (cand_sum.get("by_category") or {}).get(cat) or {}
        category_delta[cat] = {
            "recall_at_k_delta": round(float(c_cat.get("recall_at_k") or 0) - float(b_cat.get("recall_at_k") or 0), 4),
            "mrr_delta": round(float(c_cat.get("mrr") or 0) - float(b_cat.get("mrr") or 0), 4),
            "ndcg_at_k_delta": round(
                float(c_cat.get("ndcg_at_k") or 0) - float(b_cat.get("ndcg_at_k") or 0), 4
            ),
            "baseline_recall": b_cat.get("recall_at_k"),
            "candidate_recall": c_cat.get("recall_at_k"),
        }

    return {
        "baseline": fmt_provenance(baseline),
        "candidate": fmt_provenance(candidate),
        "summary_delta": {
            "recall_at_k_delta": round(float(cand_sum.get("recall_at_k") or 0) - float(base_sum.get("recall_at_k") or 0), 4),
            "mrr_delta": round(float(cand_sum.get("mrr") or 0) - float(base_sum.get("mrr") or 0), 4),
            "ndcg_at_k_delta": round(
                float(cand_sum.get("ndcg_at_k") or 0) - float(base_sum.get("ndcg_at_k") or 0), 4
            ),
            "baseline": {
                "recall_at_k": base_sum.get("recall_at_k"),
                "mrr": base_sum.get("mrr"),
                "ndcg_at_k": base_sum.get("ndcg_at_k"),
                "count": base_sum.get("count"),
            },
            "candidate": {
                "recall_at_k": cand_sum.get("recall_at_k"),
                "mrr": cand_sum.get("mrr"),
                "ndcg_at_k": cand_sum.get("ndcg_at_k"),
                "count": cand_sum.get("count"),
            },
        },
        "by_category": category_delta,
        "regressions": regressions,
        "improvements": improvements,
        "rank_changes_count": len(rank_changes),
        "top_rank_changes": sorted(rank_changes, key=lambda row: abs(row["delta_mrr"]), reverse=True)[:15],
    }


def print_human(diff: dict) -> None:
    print("=== RAG 评测对比 ===")
    print(f"基准: {diff['baseline']}")
    print(f"候选: {diff['candidate']}")
    print()
    sd = diff["summary_delta"]
    print(
        f"Recall@k: {sd['baseline']['recall_at_k']} → {sd['candidate']['recall_at_k']} "
        f"(Δ {sd['recall_at_k_delta']:+.4f})"
    )
    print(f"MRR:      {sd['baseline']['mrr']} → {sd['candidate']['mrr']} (Δ {sd['mrr_delta']:+.4f})")
    print(
        f"nDCG@k:   {sd['baseline'].get('ndcg_at_k')} → {sd['candidate'].get('ndcg_at_k')} "
        f"(Δ {sd.get('ndcg_at_k_delta', 0):+.4f})"
    )
    print()
    if diff["by_category"]:
        print("--- 分题型 Δ ---")
        for cat, row in diff["by_category"].items():
            print(
                f"  {cat}: recall Δ {row['recall_at_k_delta']:+.4f}, "
                f"mrr Δ {row['mrr_delta']:+.4f}, "
                f"ndcg Δ {row.get('ndcg_at_k_delta', 0):+.4f}"
            )
        print()
    print(f"回归（命中→未命中）: {len(diff['regressions'])} 题")
    for row in diff["regressions"][:10]:
        print(f"  {row['id']}: {row['question'][:40]}…")
    print(f"提升（未命中→命中）: {len(diff['improvements'])} 题")
    for row in diff["improvements"][:10]:
        print(f"  {row['id']}: {row['question'][:40]}…")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two RAG eval report.json files")
    parser.add_argument("baseline", type=Path, help="基准 report.json")
    parser.add_argument("candidate", type=Path, help="候选 report.json")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("-o", "--out", type=Path, default=None, help="写入对比结果 JSON")
    args = parser.parse_args()

    baseline = load_report(args.baseline)
    candidate = load_report(args.candidate)
    diff = compare_reports(baseline, candidate)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")

    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print_human(diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
