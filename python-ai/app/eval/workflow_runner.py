"""W6-6 审查工作流轨迹评测：看节点/工具/参数/确认，不看文笔。不调 LLM。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.budget import BudgetLimits, use_limits
from app.agents.graph import run_review_workflow
from app.agents.intent import wants_review_graph, wants_tool_loop
from app.eval.selection import normalize_categories, select_items
from app.schemas.tools import ToolInvokeResponse

ProgressCallback = Callable[[int, int, str], None]
TASK_ID = "w6_workflow"


def load_golden(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ok(name: str, result: dict[str, Any]) -> ToolInvokeResponse:
    return ToolInvokeResponse(name=name, ok=True, stop=False, result=result)


def _fail(name: str, message: str, *, error_code: str = "missing", result: dict | None = None) -> ToolInvokeResponse:
    return ToolInvokeResponse(
        name=name,
        ok=False,
        stop=True,
        result=result or {},
        error=message,
        error_code=error_code,  # type: ignore[arg-type]
    )


def _scripted_table(**overrides: ToolInvokeResponse) -> dict[str, ToolInvokeResponse]:
    table = {
        "list_scope": _ok(
            "list_scope",
            {
                "ok": True,
                "companies": ["002594", "601633"],
                "items": [
                    {
                        "company_code": "002594",
                        "year": 2024,
                        "scope": "consolidated",
                        "concepts": ["revenue", "net_profit"],
                    },
                    {
                        "company_code": "601633",
                        "year": 2024,
                        "scope": "consolidated",
                        "concepts": ["revenue", "net_profit"],
                    },
                ],
            },
        ),
        "compare_peers": _ok(
            "compare_peers",
            {
                "ok": True,
                "lookups": [
                    {
                        "ok": True,
                        "company_code": "002594",
                        "concept": "net_profit",
                        "year": 2024,
                        "scope": "consolidated",
                        "value_yuan": "41587940000",
                        "doc_id": "002594_2024",
                        "status": "auto_accepted",
                    },
                    {
                        "ok": True,
                        "company_code": "601633",
                        "concept": "net_profit",
                        "year": 2024,
                        "scope": "consolidated",
                        "value_yuan": "12660012515.78",
                        "doc_id": "601633_2024",
                        "status": "auto_accepted",
                    },
                ],
            },
        ),
        "verify_number": _ok(
            "verify_number",
            {"ok": True, "stop": False, "verdict": "match", "lookup_outcome": "ok", "message": "match"},
        ),
        "rag_search": _ok(
            "rag_search",
            {
                "ok": True,
                "outcome": "ok",
                "citations": [
                    {
                        "doc_id": "002594_2024",
                        "page": 20,
                        "snippet": "净利润变动主要来自销量与产品结构。",
                        "title": "比亚迪2024年年度报告",
                    }
                ],
            },
        ),
        "emit_conclusion": _ok(
            "emit_conclusion",
            {
                "ok": True,
                "conclusion": {
                    "conclusion": "ok",
                    "risk_level": "低",
                    "clause_refs": ["002594_2024#p20"],
                    "confidence": 0.72,
                },
            },
        ),
        "create_review_draft": _ok(
            "create_review_draft",
            {
                "ok": True,
                "stop": False,
                "draft_id": "11111111-1111-1111-1111-111111111111",
                "status": "PENDING",
                "replayed": False,
                "message": "已写入 PENDING 审查工单草稿",
            },
        ),
    }
    table.update(overrides)
    return table


def _override(name: str, mode: str) -> ToolInvokeResponse:
    if mode == "ok":
        return _scripted_table()[name]
    if mode == "timeout":
        return _fail(name, "upstream timeout", error_code="timeout")
    if mode == "unauthorized":
        return _fail(name, "forbidden", error_code="unauthorized")
    if mode == "empty_rag":
        return _ok(name, {"ok": True, "outcome": "ok", "citations": []})
    if mode == "mismatch":
        return _ok(name, {"ok": True, "verdict": "mismatch", "message": "对不上"})
    return _fail(name, "至少一家无数据", error_code="missing", result={"ok": False, "lookups": []})


def resolve_entry(question: str) -> str:
    if wants_review_graph(question):
        return "graph"
    if wants_tool_loop(question):
        return "tools"
    return "asknum"


def _nodes(trace: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("node")) for item in trace if item.get("node") and item.get("node") != "number_check"]


def _fail_node(trace: list[dict[str, Any]]) -> str | None:
    failed = [item for item in trace if item.get("node") and item.get("ok") is False]
    if failed:
        return str(failed[-1].get("node"))
    nodes = _nodes(trace)
    return nodes[-1] if nodes else None


def run_item(item: dict[str, Any]) -> dict[str, Any]:
    question = str(item.get("question") or "")
    expected_entry = str(item.get("expected_entry") or "graph")
    actual_entry = resolve_entry(question)
    problems: list[str] = []
    if expected_entry != "graph":
        if actual_entry != expected_entry:
            problems.append(f"入口期望 {expected_entry} 实际 {actual_entry}")
        return {
            "id": item["id"],
            "category": item.get("category"),
            "question": question,
            "expected_entry": expected_entry,
            "actual_entry": actual_entry,
            "expected_route": item.get("expected_route"),
            "actual_route": None,
            "expected_nodes": item.get("expected_nodes"),
            "actual_nodes": [],
            "calls": [],
            "draft_id": None,
            "fail_node": None,
            "steps": 0,
            "confirmed": False,
            "passed": not problems,
            "status": "pass" if not problems else "fail",
            "detail": "；".join(problems) if problems else "通过",
        }

    overrides: dict[str, ToolInvokeResponse] = {}
    for name, mode in (item.get("tools") or {}).items():
        overrides[str(name)] = _override(str(name), str(mode))
    table = _scripted_table(**overrides)
    calls: list[dict[str, Any]] = []

    def _call(name, arguments, request_id=None, **_kwargs):
        calls.append({"name": name, "arguments": dict(arguments or {})})
        if name not in table:
            return ToolInvokeResponse(
                name=name,
                ok=False,
                stop=True,
                result={},
                error=f"未挂载工具 {name}",
                error_code="unknown_tool",
            )
        return table[name]

    saver = InMemorySaver()
    thread_id: str | None = None
    last = None
    limits = BudgetLimits.from_settings()
    updates: dict[str, Any] = {}
    if item.get("max_tool_calls") is not None:
        updates["max_tool_calls"] = int(item["max_tool_calls"])
    if item.get("max_time_ms") is not None:
        updates["max_time_ms"] = float(item["max_time_ms"])
    if updates:
        limits = BudgetLimits(**{**limits.__dict__, **updates})
    actions = item.get("actions") or [{"type": "start"}]
    with patch("app.agents.graph.call_tool", _call), use_limits(limits):
        for raw in actions:
            step = raw if isinstance(raw, dict) else {"type": str(raw)}
            action = str(step.get("type") or "start")
            dept = str(step.get("dept") or item.get("dept") or "research")
            if action == "start":
                last = run_review_workflow(
                    str(step.get("question") or question),
                    checkpointer=saver,
                    dept=dept,
                )
                thread_id = last.thread_id
            elif action == "resume":
                last = run_review_workflow(
                    str(step.get("question") or "确认"),
                    checkpointer=saver,
                    thread_id=str(step.get("thread_id") or thread_id or ""),
                    dept=dept,
                    action="resume",
                )
            elif action == "cancel":
                last = run_review_workflow(
                    str(step.get("question") or "取消"),
                    checkpointer=saver,
                    thread_id=str(step.get("thread_id") or thread_id or ""),
                    dept=dept,
                    action="cancel",
                )
            else:
                problems.append(f"未知动作 {action}")
    assert last is not None
    names = [row["name"] for row in calls]
    nodes = _nodes(list(last.trace or []))
    expected_nodes = [str(item) for item in (item.get("expected_nodes") or [])]
    if expected_nodes and nodes != expected_nodes:
        problems.append(f"节点期望 {expected_nodes} 实际 {nodes}")
    expected_route = item.get("expected_route")
    if expected_route and last.route != expected_route:
        problems.append(f"路由期望 {expected_route} 实际 {last.route}")
    for name in item.get("expected_tools") or []:
        if name not in names:
            problems.append(f"缺少工具 {name}")
    for name in item.get("forbidden_tools") or []:
        if name in names:
            problems.append(f"禁止调用了 {name}")
    for name, count in (item.get("expected_tool_counts") or {}).items():
        actual = names.count(str(name))
        if actual != int(count):
            problems.append(f"{name} 调用次数期望 {count} 实际 {actual}")
    for name, want in (item.get("expected_params") or {}).items():
        matched = next((row["arguments"] for row in calls if row["name"] == name), None)
        if matched is None:
            problems.append(f"{name} 未调用，无法核对参数")
            continue
        for key, value in want.items():
            if matched.get(key) != value:
                problems.append(f"{name}.{key} 期望 {value} 实际 {matched.get(key)}")
    expect_draft = item.get("expect_draft")
    if expect_draft is True and not last.draft_id:
        problems.append("期望写入草稿但没有 draft_id")
    if expect_draft is False and last.draft_id:
        problems.append(f"不应写草稿，实际 {last.draft_id}")
    for snippet in item.get("expected_reply_contains") or []:
        if snippet not in (last.reply or ""):
            problems.append(f"回复缺少「{snippet}」")
    for snippet in item.get("expected_stop_contains") or []:
        blob = f"{last.stop_reason or ''} {last.reply or ''}"
        if snippet not in blob:
            problems.append(f"停止原因缺少「{snippet}」")
    confirmed = any(str((raw if isinstance(raw, dict) else {"type": raw}).get("type")) == "resume" for raw in actions)
    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": question,
        "expected_entry": expected_entry,
        "actual_entry": actual_entry,
        "expected_route": expected_route,
        "actual_route": last.route,
        "expected_nodes": expected_nodes or None,
        "actual_nodes": nodes,
        "calls": names,
        "draft_id": last.draft_id,
        "fail_node": _fail_node(list(last.trace or [])),
        "steps": len(nodes),
        "confirmed": confirmed,
        "expect_draft": item.get("expect_draft"),
        "passed": not problems,
        "status": "pass" if not problems else "fail",
        "detail": "；".join(problems) if problems else "通过",
        "reply": (last.reply or "")[:400],
        "stop_reason": last.stop_reason,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for row in results if row["passed"])
    graph_rows = [row for row in results if row.get("expected_entry") == "graph"]
    param_fail = sum(
        1
        for row in graph_rows
        if "参数" in str(row.get("detail")) or "无法核对参数" in str(row.get("detail"))
    )
    attempted = [
        row
        for row in results
        if row.get("confirmed") and row.get("expected_entry") == "graph" and row.get("expect_draft") is True
    ]
    wrote = [row for row in attempted if row.get("draft_id")]
    steps = [int(row["steps"]) for row in graph_rows if row.get("steps")]
    fail_by_node: dict[str, int] = {}
    for row in results:
        if row["passed"]:
            continue
        node = str(row.get("fail_node") or "unknown")
        fail_by_node[node] = fail_by_node.get(node, 0) + 1
    by_category: dict[str, dict[str, int]] = {}
    for row in results:
        category = str(row.get("category") or "unknown")
        bucket = by_category.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "accuracy": rate(passed, total),
        "param_accuracy": rate(len(graph_rows) - param_fail, len(graph_rows)),
        "avg_steps": round(sum(steps) / len(steps), 2) if steps else 0.0,
        "confirmation_rate": rate(len(wrote), len(attempted)),
        "fail_by_node": fail_by_node,
        "by_category": by_category,
    }


def run_workflow_eval(
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
        "# W6-6 审查工作流轨迹报告",
        "",
        f"- 黄金集：{report['golden_file']}（{report.get('golden_version')}）",
        f"- 生成时间：{report['generated_at']}",
        f"- 样本数：{summary['total']}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 | 含义 |",
        "|------|------|------|",
        f"| accuracy | {summary['accuracy']:.2%} | 入口/节点/工具/路由符合预期 |",
        f"| param_accuracy | {summary['param_accuracy']:.2%} | 关键工具参数正确 |",
        f"| avg_steps | {summary['avg_steps']} | 图节点平均数（不含数字校验） |",
        f"| confirmation_rate | {summary['confirmation_rate']:.2%} | 确认后续跑且写出草稿 |",
        "",
        "## 按题型",
        "",
        "| 题型 | 样本 | 通过 | 失败 |",
        "|------|------|------|------|",
    ]
    for category, row in (summary.get("by_category") or {}).items():
        lines.append(f"| {category} | {row['total']} | {row['passed']} | {row['failed']} |")
    lines += ["", "## 失败定位到节点", ""]
    fail_by_node = summary.get("fail_by_node") or {}
    if not fail_by_node:
        lines.append("无。")
    else:
        lines += ["| 节点 | 次数 |", "|------|------|"]
        for node, count in fail_by_node.items():
            lines.append(f"| {node} | {count} |")
    failures = [row for row in report["results"] if not row["passed"]]
    lines += ["", "## 评测失败", ""]
    if not failures:
        lines.append("无。")
    else:
        lines += ["| 样例 | 节点 | 说明 |", "|------|------|------|"]
        for row in failures:
            lines.append(
                f"| {row['id']} | {row.get('fail_node') or '—'} | {str(row['detail']).replace('|', '\\|')} |"
            )
    return "\n".join(lines) + "\n"
