"""多公司 RAG 范围与证据门评测；不调模型、不连向量库。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.asknum.slots import parse_slots
from app.eval.selection import normalize_categories, select_items
from app.rag.company_scope import company_code_from_doc_id
from app.rag.comparison import plan_comparison_scope
from app.rag.dept_scope import DEFAULT_CORPUS_DOC_IDS

ProgressCallback = Callable[[int, int, str], None]
COMPARE_OUTCOMES = ("rag_compare", "rag_compare_blocked")


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_item(
    item: dict[str, Any],
    *,
    default_corpus: list[str],
    min_hits_per_company: int = 1,
) -> dict[str, Any]:
    question = str(item["question"])
    dept = item.get("dept")
    slots = parse_slots(question)
    corpus = [str(value) for value in (item.get("corpus_doc_ids") or default_corpus)]
    expected_outcome = str(item["expected_outcome"])
    expected_companies = [str(value) for value in item.get("expected_companies") or []]
    expected_years = [int(value) for value in item.get("expected_years") or []]
    evidence_counts = {
        str(code): int(count)
        for code, count in (item.get("evidence_counts") or {}).items()
    }

    plan = plan_comparison_scope(slots=slots, all_doc_ids=corpus, dept=dept)
    actual_companies = list(slots.company_codes)
    actual_years = list(plan.selected_years)
    effective_counts = {
        code: evidence_counts.get(code, 1)
        for code in slots.company_codes
    }
    gate_failures = {
        code: "no_docs" if code in plan.missing else "low_evidence"
        for code in slots.company_codes
        if code in plan.missing or effective_counts[code] < min_hits_per_company
    }
    actual_outcome = "rag_compare_blocked" if gate_failures else "rag_compare"

    scope_leaks: list[str] = []
    for code, doc_ids in plan.company_doc_ids.items():
        for doc_id in doc_ids:
            actual_code = company_code_from_doc_id(doc_id)
            if actual_code != code:
                scope_leaks.append(doc_id)

    route_ok = actual_outcome == expected_outcome
    companies_ok = actual_companies == expected_companies
    years_ok = actual_years == expected_years
    scope_ok = not scope_leaks
    passed = route_ok and companies_ok and years_ok and scope_ok
    false_compare = expected_outcome == "rag_compare_blocked" and actual_outcome == "rag_compare"

    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": question,
        "dept": dept,
        "expected_outcome": expected_outcome,
        "actual_outcome": actual_outcome,
        "expected_companies": expected_companies,
        "actual_companies": actual_companies,
        "expected_years": expected_years,
        "actual_years": actual_years,
        "company_doc_ids": {
            code: list(doc_ids) for code, doc_ids in plan.company_doc_ids.items()
        },
        "evidence_counts": effective_counts,
        "gate_failures": gate_failures,
        "scope_leaks": scope_leaks,
        "route_ok": route_ok,
        "companies_ok": companies_ok,
        "years_ok": years_ok,
        "scope_ok": scope_ok,
        "false_compare": false_compare,
        "passed": passed,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    route_passed = sum(1 for row in results if row["route_ok"])
    company_scope_passed = sum(
        1 for row in results if row["companies_ok"] and row["scope_ok"]
    )
    period_passed = sum(1 for row in results if row["years_ok"])
    false_compares = sum(1 for row in results if row["false_compare"])
    by_category: dict[str, dict[str, int | float]] = {}
    for row in results:
        category = str(row.get("category") or "other")
        bucket = by_category.setdefault(category, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1
    for bucket in by_category.values():
        count = int(bucket["total"])
        bucket["accuracy"] = round(int(bucket["passed"]) / count, 4) if count else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "route_accuracy": round(route_passed / total, 4) if total else 0.0,
        "company_scope_accuracy": round(company_scope_passed / total, 4) if total else 0.0,
        "period_accuracy": round(period_passed / total, 4) if total else 0.0,
        "false_compare_rate": round(false_compares / total, 4) if total else 0.0,
        "by_category": by_category,
    }


def run_rag_compare_eval(
    *,
    golden_path: Path,
    limit: int = 0,
    category: str = "",
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
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

    params = golden.get("default_params") or {}
    corpus = [
        str(value)
        for value in (params.get("corpus_doc_ids") or DEFAULT_CORPUS_DOC_IDS)
    ]
    min_hits = int(params.get("min_hits_per_company") or 1)
    results: list[dict[str, Any]] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        if on_progress:
            on_progress(index, total, str(item["id"]))
        results.append(
            run_item(
                item,
                default_corpus=corpus,
                min_hits_per_company=min_hits,
            )
        )

    from app.eval.provenance import build_provenance

    return {
        "task_id": "rag_compare",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {
            "limit": limit,
            "categories": resolved_categories or None,
            "item_ids": item_ids or None,
            "min_hits_per_company": min_hits,
        },
        "provenance": build_provenance(golden_path=golden_path),
        "summary": summarize(results),
        "results": results,
    }
