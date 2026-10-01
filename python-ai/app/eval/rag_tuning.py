"""固定黄金集上的 RAG 重排候选数寻优。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.eval.rag_retrieval_runner import run_rag_retrieval_eval

ProgressCallback = Callable[[str, int, int, str], None]

COMPARE_CATEGORIES = [
    "product_enum",
    "segment_business",
    "compliance_risk",
    "governance",
    "esg_sustainability",
    "strategy_outlook",
]


def _headline(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    return {
        "count": summary["count"],
        "recall_at_k": summary["recall_at_k"],
        "mrr": summary["mrr"],
        "ndcg_at_k": summary["ndcg_at_k"],
        "citation_accuracy": summary["citation_accuracy"],
        "latency_p50_ms": summary["latency_p50_ms"],
        "latency_p95_ms": summary["latency_p95_ms"],
        "latency_mean_ms": summary["latency_mean_ms"],
        "rerank_fallback_count": sum(
            1 for row in report.get("results") or [] if row.get("rerank_fallback")
        ),
    }


def select_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """质量在最优值 1 个百分点内时优先选 P95 更低的候选数。"""
    if not rows:
        raise ValueError("no tuning rows")
    best_recall = max(float(row["recall_at_k"]) for row in rows)
    best_ndcg = max(float(row["ndcg_at_k"]) for row in rows)
    eligible = [
        row
        for row in rows
        if float(row["recall_at_k"]) >= best_recall - 0.01
        and float(row["ndcg_at_k"]) >= best_ndcg - 0.01
        and int(row["rerank_fallback_count"]) == 0
    ]
    if not eligible:
        eligible = rows
    return min(
        eligible,
        key=lambda row: (
            float(row["latency_p95_ms"]),
            float(row["latency_p50_ms"]),
            int(row["rerank_candidates"]),
        ),
    )


def _run_profile(
    *,
    name: str,
    golden_path: Path,
    candidates: list[int],
    top_k: int,
    categories: list[str] | None,
    item_ids: list[str] | None,
    limit: int,
    on_progress: ProgressCallback | None,
) -> dict[str, Any]:
    if item_ids and categories:
        allowed = set(categories)
        payload = json.loads(golden_path.read_text(encoding="utf-8"))
        category_by_id = {
            str(item["id"]): str(item.get("category") or "")
            for item in payload.get("items") or []
        }
        item_ids = [item_id for item_id in item_ids if category_by_id.get(item_id) in allowed]
    rows: list[dict[str, Any]] = []
    reports: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        def progress(done: int, total: int, item_id: str, *, value: int = candidate) -> None:
            if on_progress:
                on_progress(f"{name}:{value}", done, total, item_id)

        report = run_rag_retrieval_eval(
            golden_path=golden_path,
            limit=limit,
            categories=categories,
            item_ids=item_ids,
            top_k=top_k,
            label=f"tuning-{name}-c{candidate}",
            mode="rerank",
            warmup=True,
            rerank_candidates=candidate,
            on_progress=progress,
        )
        reports[str(candidate)] = report
        rows.append({"rerank_candidates": candidate, **_headline(report)})
    selected = select_candidate(rows)
    return {"rows": rows, "selected": selected, "reports": reports}


def run_rag_tuning(
    *,
    golden_path: Path,
    candidates: list[int],
    limit: int = 0,
    items_per_category: int = 0,
    profile: str = "all",
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    unique_candidates = sorted({int(value) for value in candidates if int(value) > 0})
    if not unique_candidates:
        raise ValueError("candidates must contain positive integers")
    item_ids: list[str] | None = None
    if items_per_category > 0 and limit <= 0:
        payload = json.loads(golden_path.read_text(encoding="utf-8"))
        counts: dict[str, int] = {}
        selected: list[str] = []
        for item in payload.get("items") or []:
            category = str(item.get("category") or "")
            if counts.get(category, 0) >= items_per_category:
                continue
            counts[category] = counts.get(category, 0) + 1
            selected.append(str(item["id"]))
        item_ids = selected
    if profile not in {"all", "standard", "comparison"}:
        raise ValueError("profile must be all / standard / comparison")
    profiles: dict[str, dict[str, Any]] = {}
    if profile in {"all", "standard"}:
        profiles["standard"] = _run_profile(
            name="standard",
            golden_path=golden_path,
            candidates=unique_candidates,
            top_k=12,
            categories=None,
            item_ids=item_ids,
            limit=limit,
            on_progress=on_progress,
        )
    if profile in {"all", "comparison"}:
        profiles["comparison"] = _run_profile(
            name="comparison",
            golden_path=golden_path,
            candidates=unique_candidates,
            top_k=6,
            categories=COMPARE_CATEGORIES,
            item_ids=item_ids,
            limit=limit,
            on_progress=on_progress,
        )
    recommendation: dict[str, int] = {}
    if "standard" in profiles:
        recommendation["rag_rerank_candidates"] = profiles["standard"]["selected"][
            "rerank_candidates"
        ]
    if "comparison" in profiles:
        recommendation["rag_compare_rerank_candidates"] = profiles["comparison"][
            "selected"
        ]["rerank_candidates"]
    return {
        "task_id": "rag_tuning",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_file": golden_path.name,
        "candidates": unique_candidates,
        "items_per_category": items_per_category,
        "selection_rule": (
            "Recall 与 nDCG 距离各自最优值不超过 0.01、且无 rerank fallback；"
            "在合格配置中选择 P95 最低者"
        ),
        "profile": profile,
        "profiles": profiles,
        "recommendation": recommendation,
    }
