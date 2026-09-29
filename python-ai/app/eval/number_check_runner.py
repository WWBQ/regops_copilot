"""W6-3 数字校验黄金集 runner：抽取并回溯，不调 LLM。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.rag.evidence import BLOCK_STATUSES, check_reply, pack_from_facts_and_snippets
from app.eval.selection import normalize_categories, select_items

ProgressCallback = Callable[[int, int, str], None]

TASK_ID = "w6_number_check"


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    pack = pack_from_facts_and_snippets(item.get("facts") or [], item.get("snippets") or [])
    checked = check_reply(str(item.get("reply") or ""), pack)
    expected_ok = bool(item["expected_ok"])
    actual_ok = checked.ok
    blocked = [
        {"text": row.claim.text, "status": row.status, "detail": row.detail} for row in checked.blocked
    ]
    blocked_statuses = [row["status"] for row in blocked]
    expected_categories = [str(item) for item in (item.get("expected_categories") or [])]
    problems: list[str] = []
    if actual_ok != expected_ok:
        problems.append(f"ok 期望 {expected_ok} 实际 {actual_ok}")
    missing = [name for name in expected_categories if name not in blocked_statuses]
    if missing:
        problems.append(f"未命中类别 {missing} 实际 {blocked_statuses}")
    by_status = {name: 0 for name in BLOCK_STATUSES}
    for row in checked.claims:
        if row.status in by_status:
            by_status[row.status] += 1
    passed = not problems
    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": item.get("question"),
        "expected_ok": expected_ok,
        "actual_ok": actual_ok,
        "expected_categories": expected_categories or None,
        "blocked": blocked,
        "claim_count": len(checked.claims),
        "blocked_count": len(blocked),
        "unit_error": by_status["unit_error"],
        "percent_scale": by_status["percent_scale"],
        "computed": by_status["computed"],
        "unbacked": by_status["unbacked"],
        "passed": passed,
        "status": "pass" if passed else "fail",
        "detail": "；".join(problems) if problems else "通过",
        "reply": item.get("reply"),
        "checked_reply": checked.reply if not actual_ok else None,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    should_block = [row for row in results if row["expected_ok"] is False]
    should_pass = [row for row in results if row["expected_ok"] is True]
    false_accept = sum(1 for row in should_block if row["actual_ok"])
    false_reject = sum(1 for row in should_pass if not row["actual_ok"])
    claim_total = sum(int(row["claim_count"]) for row in results)
    blocked_claims = sum(int(row["blocked_count"]) for row in results)
    unit_items = sum(1 for row in results if row["unit_error"] or row["percent_scale"])
    unit_claims = sum(int(row["unit_error"]) + int(row["percent_scale"]) for row in results)

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
        "false_accept": false_accept,
        "false_accept_rate": rate(false_accept, len(should_block)),
        "false_reject": false_reject,
        "false_reject_rate": rate(false_reject, len(should_pass)),
        "number_error_rate": rate(blocked_claims, claim_total),
        "unit_error_count": unit_claims,
        "unit_error_rate": rate(unit_items, total),
        "computed_count": sum(int(row["computed"]) for row in results),
        "unbacked_count": sum(int(row["unbacked"]) for row in results),
        "claim_total": claim_total,
        "blocked_claims": blocked_claims,
        "by_category": by_category,
    }


def run_number_check_eval(
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
        "# W6-3 数字校验黄金集报告",
        "",
        f"- 黄金集：{report['golden_file']}（{report.get('golden_version')}）",
        f"- 生成时间：{report['generated_at']}",
        f"- 样本数：{summary['total']}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 | 含义 |",
        "|------|------|------|",
        f"| accuracy | {summary['accuracy']:.2%} | 放行/拦截方向与类别符合预期 |",
        f"| false_accept_rate | {summary['false_accept_rate']:.2%} | 误放行：应拦截却放行（必须为 0） |",
        f"| false_reject_rate | {summary['false_reject_rate']:.2%} | 有证据却被拦 |",
        f"| number_error_rate | {summary['number_error_rate']:.2%} | 抽取数字中无法回溯的比例（与准确率分开） |",
        f"| unit_error_rate | {summary['unit_error_rate']:.2%} | 含万元/亿元或百分数量纲问题的样本占比 |",
        "",
        "## 按题型",
        "",
        "| 题型 | 样本 | 通过 | 失败 |",
        "|------|------|------|------|",
    ]
    for category, row in (summary.get("by_category") or {}).items():
        lines.append(f"| {category} | {row['total']} | {row['passed']} | {row['failed']} |")

    blocked = [row for row in report["results"] if not row["actual_ok"]]
    lines += ["", "## 拦截样例（可复现）", ""]
    if not blocked:
        lines.append("无。")
    else:
        lines += ["| 样例 | 类别 | 拦截 | 说明 |", "|------|------|------|------|"]
        for row in blocked:
            kinds = ",".join(item["status"] for item in row.get("blocked") or []) or "—"
            detail = str(row["detail"]).replace("|", "\\|")
            lines.append(f"| {row['id']} | {row.get('category')} | {kinds} | {detail} |")

    failures = [row for row in report["results"] if not row["passed"]]
    lines += ["", "## 评测失败", ""]
    if not failures:
        lines.append("无。")
    else:
        lines += ["| 样例 | 说明 |", "|------|------|"]
        for row in failures:
            lines.append(f"| {row['id']} | {str(row['detail']).replace('|', '\\|')} |")
    return "\n".join(lines) + "\n"
