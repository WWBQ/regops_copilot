"""检索守卫评测：部门 ACL 与无答案拒答。不调 LLM、不连向量库。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.eval.selection import normalize_categories, select_items
from app.rag.company_scope import company_code_from_doc_id
from app.rag.dept_scope import DEFAULT_CORPUS_DOC_IDS, apply_retrieval_scope
from app.rag.service import should_use_rag

ProgressCallback = Callable[[int, int, str], None]
GUARD_OUTCOMES = ("no_intent", "no_docs", "retrieve")


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def decide_guard(
    question: str,
    *,
    dept: str | None = None,
    corpus: list[str] | None = None,
) -> tuple[str, list[str]]:
    if not should_use_rag(question):
        return "no_intent", []
    scoped = apply_retrieval_scope(list(corpus or DEFAULT_CORPUS_DOC_IDS), question, dept)
    if not scoped:
        return "no_docs", []
    return "retrieve", scoped


def _companies(doc_ids: list[str]) -> list[str]:
    codes = []
    for doc_id in doc_ids:
        code = company_code_from_doc_id(doc_id)
        if code and code not in codes:
            codes.append(code)
    return codes


def run_item(item: dict[str, Any], *, corpus: list[str]) -> dict[str, Any]:
    question = str(item["question"])
    dept = item.get("dept")
    expected_outcome = str(item.get("expected_outcome") or "")
    expected_companies = [str(code) for code in (item.get("expected_companies") or [])]
    forbidden = {str(code) for code in (item.get("forbidden_companies") or [])}

    outcome, scoped = decide_guard(question, dept=dept, corpus=corpus)
    actual_companies = _companies(scoped)
    leaked = [code for code in actual_companies if code in forbidden]
    outcome_ok = outcome == expected_outcome
    companies_ok = set(actual_companies) == set(expected_companies)
    leak_ok = not leaked
    passed = outcome_ok and companies_ok and leak_ok
    if expected_outcome in {"no_intent", "no_docs"} and outcome == "retrieve":
        false_accept = True
    else:
        false_accept = False

    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": question,
        "dept": dept,
        "expected_outcome": expected_outcome,
        "actual_outcome": outcome,
        "expected_companies": expected_companies,
        "actual_companies": actual_companies,
        "forbidden_companies": sorted(forbidden),
        "leaked_companies": leaked,
        "scoped_doc_ids": scoped,
        "outcome_ok": outcome_ok,
        "companies_ok": companies_ok,
        "false_accept": false_accept,
        "passed": passed,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    false_accept = sum(1 for row in results if row["false_accept"])
    leaks = sum(1 for row in results if row["leaked_companies"])
    by_category: dict[str, dict[str, int | float]] = {}
    for row in results:
        cat = str(row.get("category") or "other")
        bucket = by_category.setdefault(cat, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    for bucket in by_category.values():
        n = int(bucket["total"])
        bucket["accuracy"] = round(int(bucket["passed"]) / n, 4) if n else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "false_accept_rate": round(false_accept / total, 4) if total else 0.0,
        "leak_rate": round(leaks / total, 4) if total else 0.0,
        "by_category": by_category,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        f"# {report.get('task_id', 'rag_guard')}",
        "",
        f"- 时间：{str(report.get('generated_at') or '')[:19].replace('T', ' ')}",
        f"- 黄金集：`{report.get('golden_file')}` n={summary.get('total', 0)}",
        f"- 准确率 {summary.get('accuracy', 0):.1%} · 误放行 {summary.get('false_accept_rate', 0):.1%} · 泄露 {summary.get('leak_rate', 0):.1%}",
        "",
        "| 题型 | n | 通过 | 准确率 |",
        "|---|---:|---:|---:|",
    ]
    for cat, row in (summary.get("by_category") or {}).items():
        lines.append(
            f"| {cat} | {row['total']} | {row['passed']} | {float(row.get('accuracy') or 0) * 100:.1f}% |"
        )
    fails = [row for row in report.get("results") or [] if not row["passed"]]
    if fails:
        lines.extend(["", "## 失败", ""])
        for row in fails:
            lines.append(
                f"- `{row['id']}` 期望 {row['expected_outcome']} {row['expected_companies']}，"
                f"实际 {row['actual_outcome']} {row['actual_companies']} 泄露 {row['leaked_companies']}"
            )
    return "\n".join(lines) + "\n"


def run_rag_guard_eval(
    *,
    golden_path: Path,
    task_id: str,
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
    corpus = list(golden.get("default_params", {}).get("corpus_doc_ids") or DEFAULT_CORPUS_DOC_IDS)
    results = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        if on_progress:
            on_progress(index, total, item["id"])
        results.append(run_item(item, corpus=corpus))
    from app.eval.provenance import build_provenance

    return {
        "task_id": task_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {
            "limit": limit,
            "category": resolved_categories[0] if len(resolved_categories) == 1 else None,
            "categories": resolved_categories or None,
            "item_ids": item_ids or None,
            "corpus_doc_ids": corpus,
        },
        "provenance": build_provenance(golden_path=golden_path),
        "summary": summarize(results),
        "results": results,
    }
