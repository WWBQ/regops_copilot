"""W4 问数黄金集 runner：走 try_answer，不调 LLM。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from app.asknum.lookup import AsknumResult, try_answer
from app.asknum.slots import parse_slots
from app.eval.selection import normalize_categories, select_items

ProgressCallback = Callable[[int, int, str], None]

TASK_ID = "w4_asknum"
HANDLED_ROUTES = {"metric", "metric_blocked", "metric_clarify", "skip"}

# 只抓格式化金额 / 亿元约数 / 每股收益，避免把证券代码 002594 当泄露
_LEAK_RE = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*元|"
    r"约\s*-?\d+(?:\.\d+)?\s*亿|"
    r"\d+(?:\.\d+)?\s*元/股)"
)


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _decimals_equal(expected: Any, actual: Any) -> bool:
    try:
        return Decimal(str(expected)) == Decimal(str(actual))
    except (InvalidOperation, TypeError):
        return False


def _reply_leaked_amount(reply: str | None) -> bool:
    if not reply:
        return False
    return bool(_LEAK_RE.search(reply))


def _check_slots(item: dict[str, Any], slots) -> list[str]:
    problems: list[str] = []
    if "expected_companies" in item:
        actual = sorted(slots.company_codes)
        expected = sorted(item["expected_companies"])
        if actual != expected:
            problems.append(f"公司 期望 {expected} 实际 {actual}")
    if "expected_concepts" in item:
        actual = sorted(slots.concepts)
        expected = sorted(item["expected_concepts"])
        if actual != expected:
            problems.append(f"指标 期望 {expected} 实际 {actual}")
    if item.get("expected_year") is not None and slots.year != int(item["expected_year"]):
        problems.append(f"年份 期望 {item['expected_year']} 实际 {slots.year}")
    if item.get("expected_scope") and slots.scope != item["expected_scope"]:
        problems.append(f"口径 期望 {item['expected_scope']} 实际 {slots.scope}")
    return problems


def _check_lookups(item: dict[str, Any], result: AsknumResult | None) -> list[str]:
    expected_rows = item.get("expected_lookups") or []
    if not expected_rows:
        return []
    actual = list(result.lookups) if result else []
    problems: list[str] = []
    for exp in expected_rows:
        company = exp.get("company_code")
        concept = exp.get("concept")
        scope = exp.get("scope")
        match = next(
            (
                hit
                for hit in actual
                if hit.company_code == company
                and hit.concept == concept
                and (scope is None or hit.scope == scope)
            ),
            None,
        )
        if match is None:
            problems.append(f"缺少 lookup {company}/{concept}")
            continue
        if match.outcome != exp.get("outcome"):
            problems.append(
                f"{company}/{concept} outcome 期望 {exp.get('outcome')} 实际 {match.outcome}"
            )
        if "value_yuan" in exp:
            actual_value = (
                match.row.value_yuan if match.row is not None and match.outcome == "ok" else None
            )
            if actual_value is None or not _decimals_equal(exp["value_yuan"], actual_value):
                problems.append(
                    f"{company}/{concept} 金额 期望 {exp['value_yuan']} 实际 {actual_value}"
                )
    return problems


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    question = str(item["question"])
    expected_route = str(item["expected_route"])
    result = try_answer(question, persist_trace=False)
    actual_route = result.route if result is not None else "skip"
    slots = result.slots if result is not None and result.slots is not None else parse_slots(question)
    reply = result.reply if result is not None else None

    problems = []
    route_correct = actual_route == expected_route
    if not route_correct:
        problems.append(f"route 期望 {expected_route} 实际 {actual_route}")
    problems.extend(_check_slots(item, slots))
    problems.extend(_check_lookups(item, result))

    leaked = _reply_leaked_amount(reply)
    expect_no_amount = item.get("expect_no_amount")
    if expect_no_amount is None:
        expect_no_amount = expected_route in {"metric_blocked", "metric_clarify", "skip"}
    if expect_no_amount and leaked:
        problems.append("拦截路径回复中出现金额（数字泄露）")

    passed = not problems
    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": question,
        "expected_route": expected_route,
        "actual_route": actual_route,
        "route_correct": route_correct,
        "leaked": leaked,
        "passed": passed,
        "status": "pass" if passed else "fail",
        "detail": "；".join(problems) if problems else "通过",
        "lookups": [hit.to_trace_dict() for hit in (result.lookups if result else ())],
        "reply": reply,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    route_correct = sum(1 for row in results if row["route_correct"])
    no_amount_items = [
        row
        for row in results
        if row["expected_route"] in {"metric_blocked", "metric_clarify", "skip"}
    ]
    leak_count = sum(1 for row in no_amount_items if row["leaked"])

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    by_category: dict[str, dict[str, int]] = {}
    for row in results:
        category = str(row.get("category") or "unknown")
        bucket = by_category.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": rate(passed, total),
        "route_accuracy": rate(route_correct, total),
        "leak_count": leak_count,
        "leak_rate": rate(leak_count, len(no_amount_items)),
        "by_category": by_category,
    }


def run_asknum_eval(
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
        list(golden["items"]),
        categories=resolved_categories,
        item_ids=item_ids,
        limit=limit,
    )
    if not items:
        raise ValueError("没有匹配的评测题，请检查题型或题号")

    results: list[dict[str, Any]] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        if on_progress:
            on_progress(index, total, item["id"])
        results.append(run_item(item))

    return {
        "task_id": TASK_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_version": golden.get("version"),
        "golden_file": golden_path.name,
        "params": {
            "limit": limit,
            "category": resolved_categories[0] if len(resolved_categories) == 1 else None,
            "categories": resolved_categories or None,
            "item_ids": item_ids or None,
        },
        "summary": summarize(results),
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# W4 问数黄金集报告",
        "",
        f"- 黄金集：{report['golden_file']}（{report.get('golden_version')}）",
        f"- 生成时间：{report['generated_at']}",
        f"- 样本数：{summary['total']}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 | 含义 |",
        "|------|------|------|",
        f"| accuracy | {summary['accuracy']:.2%} | 路由 + 槽位 + 取值/拦截全部正确 |",
        f"| route_accuracy | {summary['route_accuracy']:.2%} | 只看 route 是否命中 |",
        f"| leak_rate | {summary['leak_rate']:.2%} | 拦截路径回复里出现金额（越低越好）|",
        "",
        "## 按题型",
        "",
        "| 题型 | 样本 | 通过 | 失败 |",
        "|------|------|------|------|",
    ]
    for category, row in (summary.get("by_category") or {}).items():
        lines.append(
            f"| {category} | {row['total']} | {row['passed']} | {row['failed']} |"
        )

    failures = [row for row in report["results"] if not row["passed"]]
    lines += ["", "## 失败样例", ""]
    if not failures:
        lines.append("无。")
    else:
        lines += ["| 样例 | 期望 | 实际 | 说明 |", "|------|------|------|------|"]
        for row in failures:
            detail = str(row["detail"]).replace("|", "\\|")
            lines.append(
                f"| {row['id']} | {row['expected_route']} | {row['actual_route']} | {detail} |"
            )
    return "\n".join(lines) + "\n"
