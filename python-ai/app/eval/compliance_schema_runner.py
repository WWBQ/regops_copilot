"""ComplianceConclusion Schema 校验黄金集 runner（W1-2）。

与 w1_chat / rag_retrieval 不同，本 runner 不依赖 LLM、网络和数据库：
直接把黄金集里的 payload 灌进 Pydantic 模型，统计放行/拒绝是否符合预期。
因此它是确定性的，可在 CI 里当回归门禁跑。

三层判定，分开统计以免互相掩盖：
- decision_correct：放行/拒绝的方向对不对 → accuracy / 误放行率 / 误拒率
- rule_matched：非法样例被拒时，报错字段与文案是否命中预期规则
  （防止「碰巧拒对了但理由是另一条约束」这种假通过）
- normalized_ok：合法样例的字段清洗结果是否符合预期（如 clause_refs 去空白）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from app.eval.selection import normalize_categories, select_items
from app.eval.schemas import ComplianceConclusion

ProgressCallback = Callable[[int, int, str], None]

TASK_ID = "compliance_schema"


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _serialize_errors(exc: ValidationError) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = tuple(err.get("loc") or ())
        rows.append(
            {
                "loc": ".".join(str(part) for part in loc),
                "field": str(loc[0]) if loc else "",
                "type": err.get("type", ""),
                "msg": err.get("msg", ""),
            }
        )
    return rows


def _check_rule_match(item: dict[str, Any], errors: list[dict[str, Any]]) -> tuple[bool, str]:
    """非法样例：报错是否指向预期的字段 / 文案。"""
    field = str(item.get("expect_error_field") or "")
    needle = str(item.get("expect_error_contains") or "")
    if not field and not needle:
        return True, "未声明期望报错，跳过理由校验"

    problems: list[str] = []
    if field and not any(err["field"] == field for err in errors):
        seen = sorted({err["field"] or "<model>" for err in errors})
        problems.append(f"期望报错字段 {field}，实际 {seen}")
    if needle and not any(needle in err["msg"] for err in errors):
        problems.append(f"期望报错含「{needle}」，实际 {[err['msg'] for err in errors]}")

    if problems:
        return False, "；".join(problems)
    return True, "报错理由命中预期规则"


def _check_normalized(
    item: dict[str, Any], model: ComplianceConclusion
) -> tuple[bool | None, str]:
    """合法样例：可选地断言字段清洗后的取值。未声明断言时返回 None（不计入统计）。"""
    expected = item.get("expect_normalized")
    if not isinstance(expected, dict) or not expected:
        return None, ""

    dumped = model.model_dump()
    problems = [
        f"{key} 期望 {value!r}，实际 {dumped.get(key)!r}"
        for key, value in expected.items()
        if dumped.get(key) != value
    ]
    if problems:
        return False, "；".join(problems)
    return True, "字段清洗符合预期"


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    expect_accept = item["category"] == "valid"

    model: ComplianceConclusion | None = None
    errors: list[dict[str, Any]] = []
    try:
        model = ComplianceConclusion.model_validate(item["payload"])
        accepted = True
    except ValidationError as exc:
        accepted = False
        errors = _serialize_errors(exc)

    decision_correct = accepted == expect_accept

    rule_matched: bool | None = None
    normalized_ok: bool | None = None
    details: list[str] = []

    if expect_accept:
        if accepted and model is not None:
            normalized_ok, note = _check_normalized(item, model)
            details.append(note or "结构校验通过")
        else:
            details.append(f"合法样例被误拒：{[err['msg'] for err in errors]}")
    else:
        if accepted:
            details.append("非法样例被误放行（false accept）")
        else:
            rule_matched, note = _check_rule_match(item, errors)
            details.append(note)

    strict_passed = decision_correct and rule_matched is not False and normalized_ok is not False

    return {
        "id": item["id"],
        "category": item["category"],
        "rule": item.get("rule"),
        "note": item.get("note", ""),
        "expected": "accept" if expect_accept else "reject",
        "actual": "accept" if accepted else "reject",
        "decision_correct": decision_correct,
        "rule_matched": rule_matched,
        "normalized_ok": normalized_ok,
        "passed": strict_passed,
        "errors": errors,
        "detail": "；".join(d for d in details if d),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    valid_items = [r for r in results if r["category"] == "valid"]
    invalid_items = [r for r in results if r["category"] == "invalid"]

    decision_correct = sum(1 for r in results if r["decision_correct"])
    # 误放行：本该拒的非法样例被放过 —— 合规场景下最危险的一类错
    false_accept = sum(1 for r in invalid_items if r["actual"] == "accept")
    # 误拒：合法样例被拦下，影响可用性
    false_reject = sum(1 for r in valid_items if r["actual"] == "reject")
    rule_hits = sum(1 for r in invalid_items if r["rule_matched"] is True)
    normalization_checked = [r for r in valid_items if r["normalized_ok"] is not None]
    normalization_passed = sum(1 for r in normalization_checked if r["normalized_ok"])
    strict_passed = sum(1 for r in results if r["passed"])

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    by_rule: list[dict[str, Any]] = []
    for rule in dict.fromkeys(r["rule"] for r in results):
        group = [r for r in results if r["rule"] == rule]
        by_rule.append(
            {
                "rule": rule,
                "total": len(group),
                "passed": sum(1 for r in group if r["passed"]),
                "failed": sum(1 for r in group if not r["passed"]),
            }
        )

    return {
        "total": total,
        "valid_total": len(valid_items),
        "invalid_total": len(invalid_items),
        "decision_correct": decision_correct,
        "accuracy": rate(decision_correct, total),
        "false_accept": false_accept,
        "false_accept_rate": rate(false_accept, len(invalid_items)),
        "false_reject": false_reject,
        "false_reject_rate": rate(false_reject, len(valid_items)),
        "rule_hit_rate": rate(rule_hits, len(invalid_items)),
        "normalization_checked": len(normalization_checked),
        "normalization_passed": normalization_passed,
        "strict_passed": strict_passed,
        "strict_pass_rate": rate(strict_passed, total),
        "by_rule": by_rule,
    }


def run_compliance_schema_eval(
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
        "schema_target": "app.eval.schemas.ComplianceConclusion",
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
        "# 合规结论 Schema 校验报告",
        "",
        f"- 校验对象：`{report['schema_target']}`",
        f"- 黄金集：{report['golden_file']}（{report.get('golden_version')}）",
        f"- 生成时间：{report['generated_at']}",
        f"- 样本数：{summary['total']}（合法 {summary['valid_total']} / 非法 {summary['invalid_total']}）",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 | 含义 |",
        "|------|------|------|",
        f"| accuracy | {summary['accuracy']:.2%} | 放行/拒绝方向判对的比例 |",
        f"| false_accept_rate | {summary['false_accept_rate']:.2%} | 非法样例被误放行（越低越好，合规红线）|",
        f"| false_reject_rate | {summary['false_reject_rate']:.2%} | 合法样例被误拒（影响可用性）|",
        f"| rule_hit_rate | {summary['rule_hit_rate']:.2%} | 非法样例被拒且报错理由命中预期规则 |",
        f"| strict_pass_rate | {summary['strict_pass_rate']:.2%} | 方向 + 理由 + 字段清洗全部正确 |",
        "",
        f"字段清洗断言：{summary['normalization_passed']}/{summary['normalization_checked']} 通过",
        "",
        "## 按规则",
        "",
        "| 规则 | 样本 | 通过 | 失败 |",
        "|------|------|------|------|",
    ]
    for row in summary["by_rule"]:
        lines.append(f"| {row['rule']} | {row['total']} | {row['passed']} | {row['failed']} |")

    failures = [r for r in report["results"] if not r["passed"]]
    lines += ["", "## 失败样例", ""]
    if not failures:
        lines.append("无。")
    else:
        lines += ["| 样例 | 规则 | 期望 | 实际 | 说明 |", "|------|------|------|------|------|"]
        for row in failures:
            detail = row["detail"].replace("|", "\\|")
            lines.append(
                f"| {row['id']} | {row['rule']} | {row['expected']} | {row['actual']} | {detail} |"
            )

    return "\n".join(lines) + "\n"
