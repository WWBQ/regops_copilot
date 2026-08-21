"""RAG 检索黄金集评测 runner。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[int, int, str], None]


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def page_hit_at_k(retrieved_pages: list[int], gold_pages: list[int], k: int) -> bool:
    if not gold_pages:
        return False
    top = retrieved_pages[:k]
    return any(page in gold_pages for page in top)


def reciprocal_rank(retrieved_pages: list[int], gold_pages: list[int], k: int) -> float:
    if not gold_pages:
        return 0.0
    for rank, page in enumerate(retrieved_pages[:k], start=1):
        if page in gold_pages:
            return 1.0 / rank
    return 0.0


def run_item(item: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    from app.rag.service import retrieve_hits_for_docs

    doc_id = item["doc_id"]
    question = item["question"]
    k = int(item.get("k", top_k))
    gold_pages = item.get("gold_pages") or []

    hits = retrieve_hits_for_docs(question=question, doc_ids=[doc_id], top_k=k)
    retrieved_pages = [int(h.metadata.get("page") or 0) for h in hits if h.metadata.get("page")]

    hit = page_hit_at_k(retrieved_pages, gold_pages, k)
    rr = reciprocal_rank(retrieved_pages, gold_pages, k)

    return {
        "id": item["id"],
        "category": item["category"],
        "question": question,
        "doc_id": doc_id,
        "gold_pages": gold_pages,
        "retrieved_pages": retrieved_pages,
        "page_hit_at_k": hit,
        "reciprocal_rank": round(rr, 4),
        "top_k": k,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"count": 0, "recall_at_k": 0.0, "mrr": 0.0, "by_category": {}}

    recall = sum(1 for row in results if row["page_hit_at_k"]) / len(results)
    mrr = sum(row["reciprocal_rank"] for row in results) / len(results)

    by_category: dict[str, dict[str, float | int]] = {}
    for row in results:
        cat = row["category"]
        bucket = by_category.setdefault(cat, {"hits": 0, "rr": 0.0, "n": 0})
        bucket["n"] += 1
        bucket["hits"] += int(row["page_hit_at_k"])
        bucket["rr"] += row["reciprocal_rank"]

    category_metrics = {
        cat: {
            "recall_at_k": round(float(v["hits"]) / float(v["n"]), 4),
            "mrr": round(float(v["rr"]) / float(v["n"]), 4),
            "count": int(v["n"]),
        }
        for cat, v in by_category.items()
    }

    return {
        "count": len(results),
        "recall_at_k": round(recall, 4),
        "mrr": round(mrr, 4),
        "by_category": category_metrics,
    }


def run_rag_retrieval_eval(
    *,
    golden_path: Path,
    limit: int = 0,
    category: str = "",
    top_k: int = 0,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    items = golden["items"]
    if category:
        items = [item for item in items if item["category"] == category]
    if limit > 0:
        items = items[:limit]
    resolved_top_k = top_k or int(golden.get("default_params", {}).get("top_k", 12))

    results: list[dict[str, Any]] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        if on_progress:
            on_progress(index, total, item["id"])
        results.append(run_item(item, top_k=resolved_top_k))

    summary = summarize(results)
    return {
        "task_id": "rag_retrieval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {"limit": limit, "category": category or None, "top_k": resolved_top_k},
        "summary": summary,
        "results": results,
    }
