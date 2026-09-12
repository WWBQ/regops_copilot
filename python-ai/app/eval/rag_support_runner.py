"""引用片段是否撑住答案：检索到的原文里有没有必须出现的证据词。

和 rag_retrieval 的页级 Recall 分开：页到了不等于清单/数字都在片段里。
不调 LLM。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.eval.selection import normalize_categories, select_items

ProgressCallback = Callable[[int, int, str], None]


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def support_coverage(blob: str, must_contain: list[str]) -> tuple[list[str], list[str]]:
    found: list[str] = []
    missing: list[str] = []
    for phrase in must_contain:
        token = str(phrase).strip()
        if not token:
            continue
        if token in blob:
            found.append(token)
        else:
            missing.append(token)
    return found, missing


def run_item(item: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    from app.rag.service import retrieve_hits_with_trace

    question = str(item["question"])
    doc_id = str(item["doc_id"])
    k = int(item.get("k") or top_k)
    must_contain = [str(token) for token in (item.get("must_contain") or []) if str(token).strip()]
    hits, pipeline = retrieve_hits_with_trace(
        question=question, doc_ids=[doc_id], top_k=k
    )
    blob = "\n".join(hit.content for hit in hits)
    found, missing = support_coverage(blob, must_contain)
    needed = len(found) + len(missing)
    coverage = round(len(found) / needed, 4) if needed else 0.0
    passed = bool(must_contain) and not missing
    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": question,
        "doc_id": doc_id,
        "must_contain": must_contain,
        "found": found,
        "missing": missing,
        "support_coverage": coverage,
        "passed": passed,
        "retrieved_pages": [int(hit.metadata.get("page") or 0) for hit in hits if hit.metadata.get("page")],
        "rerank_fallback": bool(pipeline.get("rerank_fallback")),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "count": 0,
            "support_hit_rate": 0.0,
            "support_coverage": 0.0,
            "by_category": {},
        }
    hit_rate = sum(1 for row in results if row.get("passed")) / len(results)
    coverage = sum(float(row.get("support_coverage") or 0) for row in results) / len(results)
    by_category: dict[str, dict[str, Any]] = {}
    for row in results:
        cat = str(row.get("category") or "unknown")
        bucket = by_category.setdefault(cat, {"n": 0, "hits": 0, "coverage": 0.0})
        bucket["n"] += 1
        bucket["hits"] += 1 if row.get("passed") else 0
        bucket["coverage"] += float(row.get("support_coverage") or 0)
    categories = {
        cat: {
            "count": bucket["n"],
            "support_hit_rate": round(bucket["hits"] / bucket["n"], 4),
            "support_coverage": round(bucket["coverage"] / bucket["n"], 4),
        }
        for cat, bucket in by_category.items()
    }
    return {
        "count": len(results),
        "support_hit_rate": round(hit_rate, 4),
        "support_coverage": round(coverage, 4),
        "by_category": categories,
    }


def run_rag_support_eval(
    *,
    golden_path: Path,
    limit: int = 0,
    category: str = "",
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    top_k: int = 0,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    payload = load_golden(golden_path)
    items = select_items(
        payload.get("items") or [],
        limit=limit,
        categories=normalize_categories(category, categories),
        item_ids=item_ids,
    )
    default_k = int((payload.get("default_params") or {}).get("top_k") or 12)
    resolved_k = top_k if top_k > 0 else default_k
    results: list[dict[str, Any]] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        if on_progress:
            on_progress(index - 1, total, str(item.get("id") or ""))
        results.append(run_item(item, top_k=resolved_k))
    if on_progress:
        on_progress(total, total, "")
    return {
        "task_id": "rag_support",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden": str(golden_path),
        "summary": summarize(results),
        "results": results,
    }
