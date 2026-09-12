"""RAG 检索黄金集评测 runner。"""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.eval.selection import normalize_categories, select_items
from app.rag.modes import RetrievalMode

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


def ndcg_at_k(retrieved_pages: list[int], gold_pages: list[int], k: int) -> float:
    """二元相关：gold_pages 同等相关；按首次出现的页码排序算 nDCG@k。"""
    if not gold_pages or k <= 0:
        return 0.0
    gold = {int(page) for page in gold_pages}
    ranking: list[int] = []
    seen: set[int] = set()
    for page in retrieved_pages:
        value = int(page)
        if value in seen:
            continue
        seen.add(value)
        ranking.append(value)
        if len(ranking) >= k:
            break
    dcg = 0.0
    for rank, page in enumerate(ranking, start=1):
        if page in gold:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_n = min(len(gold), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_n + 1))
    if idcg <= 0:
        return 0.0
    return round(dcg / idcg, 4)


def citation_accuracy(retrieved_pages: list[int], gold_pages: list[int], k: int) -> float:
    """页级引用准确率：top-k 去重页中属于 gold_pages 的比例。

    与 Recall@k（命中任一 gold 页即成功）互补：检索很吵时 recall 仍可能为 1，
    citation_accuracy 会偏低。无检索页时为 0。
    """
    if not gold_pages or k <= 0:
        return 0.0
    gold = {int(page) for page in gold_pages}
    ranking: list[int] = []
    seen: set[int] = set()
    for page in retrieved_pages:
        value = int(page)
        if value in seen:
            continue
        seen.add(value)
        ranking.append(value)
        if len(ranking) >= k:
            break
    if not ranking:
        return 0.0
    hits = sum(1 for page in ranking if page in gold)
    return round(hits / len(ranking), 4)


def _latency_stats(results: list[dict[str, Any]]) -> dict[str, float]:
    latencies = [float(row["latency_ms"]) for row in results if row.get("latency_ms") is not None]
    if not latencies:
        return {"latency_p50_ms": 0.0, "latency_p95_ms": 0.0, "latency_mean_ms": 0.0}
    ordered = sorted(latencies)
    p95_idx = max(0, int(len(ordered) * 0.95) - 1)
    return {
        "latency_p50_ms": round(statistics.median(latencies), 1),
        "latency_p95_ms": round(ordered[p95_idx], 1),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 1),
    }


def run_item(
    item: dict[str, Any],
    *,
    top_k: int,
    mode: RetrievalMode | None = None,
) -> dict[str, Any]:
    from app.rag.service import retrieve_hits_with_trace

    doc_id = item["doc_id"]
    question = item["question"]
    k = int(item.get("k", top_k))
    gold_pages = item.get("gold_pages") or []

    started = time.perf_counter()
    hits, pipeline = retrieve_hits_with_trace(
        question=question, doc_ids=[doc_id], top_k=k, mode=mode
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    retrieved_pages = [int(h.metadata.get("page") or 0) for h in hits if h.metadata.get("page")]

    hit = page_hit_at_k(retrieved_pages, gold_pages, k)
    rr = reciprocal_rank(retrieved_pages, gold_pages, k)
    ndcg = ndcg_at_k(retrieved_pages, gold_pages, k)
    cite_acc = citation_accuracy(retrieved_pages, gold_pages, k)
    timing = pipeline.get("timing_ms") or {}

    return {
        "id": item["id"],
        "category": item["category"],
        "question": question,
        "doc_id": doc_id,
        "gold_pages": gold_pages,
        "retrieved_pages": retrieved_pages,
        "page_hit_at_k": hit,
        "reciprocal_rank": round(rr, 4),
        "ndcg_at_k": ndcg,
        "citation_accuracy": cite_acc,
        "top_k": k,
        "mode": mode,
        "latency_ms": latency_ms,
        "timing_ms": timing,
        "rerank_fallback": bool(pipeline.get("rerank_fallback")),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "count": 0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "ndcg_at_k": 0.0,
            "citation_accuracy": 0.0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
            "latency_mean_ms": 0.0,
            "by_category": {},
        }

    recall = sum(1 for row in results if row["page_hit_at_k"]) / len(results)
    mrr = sum(row["reciprocal_rank"] for row in results) / len(results)
    ndcg = sum(float(row.get("ndcg_at_k") or 0) for row in results) / len(results)
    cite_acc = sum(float(row.get("citation_accuracy") or 0) for row in results) / len(results)

    by_category: dict[str, dict[str, float | int]] = {}
    for row in results:
        cat = row["category"]
        bucket = by_category.setdefault(
            cat, {"hits": 0, "rr": 0.0, "ndcg": 0.0, "cite": 0.0, "n": 0}
        )
        bucket["n"] += 1
        bucket["hits"] += int(row["page_hit_at_k"])
        bucket["rr"] += row["reciprocal_rank"]
        bucket["ndcg"] += float(row.get("ndcg_at_k") or 0)
        bucket["cite"] += float(row.get("citation_accuracy") or 0)

    category_metrics = {
        cat: {
            "recall_at_k": round(float(v["hits"]) / float(v["n"]), 4),
            "mrr": round(float(v["rr"]) / float(v["n"]), 4),
            "ndcg_at_k": round(float(v["ndcg"]) / float(v["n"]), 4),
            "citation_accuracy": round(float(v["cite"]) / float(v["n"]), 4),
            "count": int(v["n"]),
        }
        for cat, v in by_category.items()
    }

    return {
        "count": len(results),
        "recall_at_k": round(recall, 4),
        "mrr": round(mrr, 4),
        "ndcg_at_k": round(ndcg, 4),
        "citation_accuracy": round(cite_acc, 4),
        **_latency_stats(results),
        "by_category": category_metrics,
    }


def run_rag_retrieval_eval(
    *,
    golden_path: Path,
    limit: int = 0,
    category: str = "",
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    top_k: int = 0,
    label: str = "",
    mode: RetrievalMode | None = None,
    warmup: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    resolved_categories = normalize_categories(category, categories)
    items = select_items(
        golden["items"],
        categories=resolved_categories,
        item_ids=item_ids,
        limit=limit,
    )
    if not items:
        raise ValueError("没有匹配的评测题，请检查题型或题号")
    resolved_top_k = top_k or int(golden.get("default_params", {}).get("top_k", 12))

    if warmup:
        run_item(items[0], top_k=resolved_top_k, mode=mode)

    results: list[dict[str, Any]] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        if on_progress:
            on_progress(index, total, item["id"])
        results.append(run_item(item, top_k=resolved_top_k, mode=mode))

    summary = summarize(results)
    from app.eval.provenance import build_provenance

    return {
        "task_id": "rag_retrieval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {
            "limit": limit,
            "category": resolved_categories[0] if len(resolved_categories) == 1 else None,
            "categories": resolved_categories or None,
            "item_ids": item_ids or None,
            "top_k": resolved_top_k,
            "mode": mode,
            "warmup": warmup,
        },
        "provenance": build_provenance(
            golden_path=golden_path,
            label=label,
            extra={"retrieval_mode": mode},
        ),
        "summary": summary,
        "results": results,
    }
