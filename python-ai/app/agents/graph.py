"""w6-1/w6-2：审查对比工作流。显式 DAG + Checkpoint，不是 ReAct 让模型选边。"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents.budget import budget_message, current_meter, guard_tool, use_limits
from app.agents.checkpoint import (
    checkpoint_expired,
    get_process_checkpointer,
    graph_config,
    make_thread_id,
    normalize_dept,
    thread_belongs_to_dept,
)
from app.agents.evidence import apply_checked_reply, pack_from_workflow_values
from app.asknum.citations import facts_href
from app.asknum.slots import CONCEPT_LABELS, SCOPE_LABELS, company_display_name, parse_slots
from app.schemas.chat import Citation
from app.schemas.tools import ToolContext, ToolInvokeResponse
from app.tools.registry import invoke_tool

MAX_COMPANIES = 5


class ReviewState(TypedDict, total=False):
    question: str
    session_id: str | None
    request_id: str | None
    thread_id: str | None
    dept: str | None
    company_codes: list[str]
    concept: str | None
    year: int
    scope: str
    lookups: list[dict[str, Any]]
    verifies: list[dict[str, Any]]
    rag_citations: list[dict[str, Any]]
    conclusion: dict[str, Any] | None
    stop_reason: str | None
    reply: str
    route: str
    citations: list[dict[str, Any]]
    rag_used: bool
    draft_id: str | None
    trace: Annotated[list[dict[str, Any]], operator.add]


@dataclass(frozen=True)
class WorkflowResult:
    route: str
    reply: str
    citations: list[Citation] = field(default_factory=list)
    rag_used: bool = False
    trace: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None
    thread_id: str | None = None
    pending_node: str | None = None
    draft_id: str | None = None


def call_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    request_id: str | None = None,
    dept: str | None = None,
    idempotency_key: str | None = None,
) -> ToolInvokeResponse:
    return invoke_tool(
        name,
        arguments,
        context=ToolContext(request_id=request_id, dept=dept, idempotency_key=idempotency_key),
    )


def run_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    request_id: str | None = None,
    dept: str | None = None,
    idempotency_key: str | None = None,
) -> ToolInvokeResponse:
    return guard_tool(
        name,
        call_tool,
        name,
        arguments,
        request_id=request_id,
        dept=dept,
        idempotency_key=idempotency_key,
    )


def _step(node: str, *, tool: str | None = None, ok: bool = True, detail: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {"node": node, "ok": ok}
    if tool:
        item["tool"] = tool
    if detail:
        item["detail"] = detail
    return item


def _money(value_yuan: str) -> str:
    value = Decimal(value_yuan)
    if abs(value) >= Decimal("100000000"):
        return f"{value:,.2f} 元（约 {value / Decimal('100000000'):.2f} 亿元）"
    return f"{value:,.2f} 元"


def classify(state: ReviewState) -> dict[str, Any]:
    slots = parse_slots(state["question"])
    codes = list(slots.company_codes)
    concept = slots.concepts[0] if len(slots.concepts) == 1 else None
    stop = None
    if len(codes) < 2:
        stop = "对比审查至少需要两家已识别公司。"
    elif len(codes) > MAX_COMPANIES:
        stop = f"一次最多对比 {MAX_COMPANIES} 家，请缩小范围。"
    elif len(slots.concepts) > 1:
        stop = "一次只对比一个指标，请指定营收或净利润等其中一个。"
    elif not slots.concepts:
        stop = None  # list_scope 后再反问
    return {
        "company_codes": codes,
        "concept": concept,
        "year": slots.year,
        "scope": slots.scope,
        "stop_reason": stop,
        "trace": [_step("classify", ok=stop is None, detail=",".join(codes))],
    }


def route_after_classify(state: ReviewState) -> Literal["list_scope", "stop"]:
    return "stop" if state.get("stop_reason") else "list_scope"


def list_scope_node(state: ReviewState) -> dict[str, Any]:
    out = run_tool(
        "list_scope",
        {"year": state["year"], "scope": state["scope"], "accepted_only": True},
        request_id=state.get("request_id"),
    )
    if not out.ok:
        return {
            "stop_reason": out.error or "覆盖面查询失败。",
            "trace": [_step("list_scope", tool="list_scope", ok=False, detail=out.error or "")],
        }
    known = set(out.result.get("companies") or [])
    by_company: dict[str, set[str]] = {}
    for item in out.result.get("items") or []:
        code = str(item.get("company_code") or "")
        if item.get("year") not in (None, state["year"]):
            continue
        if item.get("scope") not in (None, state["scope"]):
            continue
        by_company.setdefault(code, set()).update(item.get("concepts") or [])
        known.add(code)
    missing = [code for code in state["company_codes"] if code not in known]
    if missing:
        names = "、".join(company_display_name(code) for code in missing)
        return {
            "stop_reason": f"覆盖面没有 {names}（{state['year']} {state['scope']}），不硬查、不插值。",
            "trace": [_step("list_scope", tool="list_scope", ok=False, detail="missing_company")],
        }
    concept = state.get("concept")
    if not concept:
        sample = sorted(next(iter(by_company.values()), set()))
        hint = "、".join(CONCEPT_LABELS.get(item, item) for item in sample[:8]) or "营收、净利润"
        return {
            "stop_reason": f"请指定要对比的指标，例如 {hint}。",
            "trace": [_step("list_scope", tool="list_scope", ok=False, detail="missing_concept")],
        }
    uncovered = [
        code for code in state["company_codes"] if concept not in by_company.get(code, set())
    ]
    if uncovered:
        names = "、".join(company_display_name(code) for code in uncovered)
        label = CONCEPT_LABELS.get(concept, concept)
        return {
            "stop_reason": f"{names} 的 {state['year']} 年覆盖面没有「{label}」，不硬查。",
            "trace": [_step("list_scope", tool="list_scope", ok=False, detail="missing_concept_coverage")],
        }
    return {"trace": [_step("list_scope", tool="list_scope", ok=True)]}


def route_after_scope(state: ReviewState) -> Literal["compare", "stop"]:
    return "stop" if state.get("stop_reason") else "compare"


def compare_node(state: ReviewState) -> dict[str, Any]:
    out = run_tool(
        "compare_peers",
        {
            "company_codes": state["company_codes"],
            "concept": state["concept"],
            "year": state["year"],
            "scope": state["scope"],
        },
        request_id=state.get("request_id"),
    )
    lookups = list(out.result.get("lookups") or [])
    if not out.ok:
        return {
            "lookups": lookups,
            "stop_reason": out.error or out.result.get("message") or "至少一家没有已通过数字，停止。",
            "trace": [_step("compare", tool="compare_peers", ok=False)],
        }
    return {
        "lookups": lookups,
        "trace": [_step("compare", tool="compare_peers", ok=True, detail=str(len(lookups)))],
    }


def route_after_compare(state: ReviewState) -> Literal["verify", "stop"]:
    return "stop" if state.get("stop_reason") else "verify"


def verify_node(state: ReviewState) -> dict[str, Any]:
    verifies: list[dict[str, Any]] = []
    for row in state.get("lookups") or []:
        claimed = row.get("value_yuan")
        if not claimed:
            return {
                "verifies": verifies,
                "stop_reason": "查数结果缺少金额，停止，不编造。",
                "trace": [_step("verify", tool="verify_number", ok=False)],
            }
        out = run_tool(
            "verify_number",
            {
                "company_code": row["company_code"],
                "concept": state["concept"],
                "year": state["year"],
                "scope": state["scope"],
                "claimed": str(claimed),
            },
            request_id=state.get("request_id"),
        )
        verifies.append(out.result)
        if not out.ok or out.result.get("verdict") != "match":
            return {
                "verifies": verifies,
                "stop_reason": out.error or out.result.get("message") or "数字核对失败，停止。",
                "trace": [_step("verify", tool="verify_number", ok=False)],
            }
    return {
        "verifies": verifies,
        "trace": [_step("verify", tool="verify_number", ok=True)],
    }


def route_after_verify(state: ReviewState) -> Literal["rag", "stop"]:
    return "stop" if state.get("stop_reason") else "rag"


def rag_node(state: ReviewState) -> dict[str, Any]:
    names = "、".join(company_display_name(code) for code in state["company_codes"])
    label = CONCEPT_LABELS.get(state["concept"] or "", state.get("concept") or "指标")
    question = (
        f"{names} {state['year']}年年报管理层讨论与分析中关于「{label}」的说明与差异原因是什么"
    )
    out = run_tool(
        "rag_search",
        {"question": question, "session_id": state.get("session_id")},
        request_id=state.get("request_id"),
    )
    citations = [item for item in (out.result.get("citations") or []) if item.get("doc_id") and int(item.get("page") or 0) >= 1]
    if not out.ok or not citations:
        return {
            "rag_citations": citations,
            "rag_used": False,
            "stop_reason": "无法引用管理层口径（缺 doc_id/页或低分拒答），停止，不编造出处。",
            "trace": [_step("rag", tool="rag_search", ok=False)],
        }
    return {
        "rag_citations": citations,
        "rag_used": True,
        "trace": [_step("rag", tool="rag_search", ok=True, detail=str(len(citations)))],
    }


def route_after_rag(state: ReviewState) -> Literal["conclude", "stop"]:
    return "stop" if state.get("stop_reason") else "conclude"


def _draft_evidence(state: ReviewState) -> dict[str, Any]:
    label = CONCEPT_LABELS.get(state.get("concept") or "", state.get("concept") or "指标")
    facts: list[str] = []
    fact_lines: list[str] = []
    rag_lines: list[str] = []
    citations: list[dict[str, Any]] = []
    for row in state.get("lookups") or []:
        code = row["company_code"]
        name = company_display_name(code)
        amount = _money(str(row["value_yuan"]))
        facts.append(f"{name} {amount}")
        mark = len(citations) + 1
        citations.append(
            {
                "doc_id": row.get("doc_id") or f"{code}_{state.get('year')}",
                "page": 1,
                "snippet": f"{name} {state.get('year')} 年「{label}」{amount}",
                "title": f"财务事实库 · {name} {label}",
                "href": facts_href(company_code=code, concept=state.get("concept"), status=row.get("status")),
                "kind": "facts",
                "mark": mark,
            }
        )
        fact_lines.append(f"- {name} {label} {amount} [{mark}]")
    for hit in state.get("rag_citations") or []:
        mark = len(citations) + 1
        snippet = str(hit.get("snippet") or "").strip()
        rag_lines.append(f"{snippet} [{mark}]")
        citations.append(
            {
                "doc_id": hit["doc_id"],
                "page": int(hit["page"]),
                "snippet": snippet,
                "title": hit.get("title"),
                "viewer_url": hit.get("viewer_url"),
                "kind": "document",
                "mark": mark,
            }
        )
    clause_refs = [f"{hit['doc_id']}#p{int(hit['page'])}" for hit in state.get("rag_citations") or []]
    names = "、".join(company_display_name(code) for code in (state.get("company_codes") or []))
    scope_label = SCOPE_LABELS.get(state.get("scope") or "", state.get("scope") or "")
    impact_scope = (
        f"{names} · {state.get('year')} 年{scope_label} · {label}"
        if names
        else f"{state.get('year')} 年 · {label}"
    )
    title = f"{state.get('year')}年{label}对比审查草稿"
    reason = "人工确认后写入 PENDING 工单，供后续 Java 复核；本步不提交 maker-checker。"
    conclusion_text = (
        f"{state.get('year')} 年「{label}」按财务事实库并列：{'；'.join(facts)}。"
        "未手算差额或比率。管理层口径见年报引用。非正式合规或投资意见。"
    )
    return {
        "label": label,
        "citations": citations,
        "fact_lines": fact_lines,
        "rag_lines": rag_lines,
        "clause_refs": clause_refs,
        "conclusion_text": conclusion_text,
        "impact_scope": impact_scope,
        "title": title,
        "reason": reason,
        "company_code": (state.get("company_codes") or [None])[0],
        "company_codes": list(state.get("company_codes") or []),
    }


def _pause_reply(state: ReviewState) -> str:
    evidence = _draft_evidence(state)
    path = " → ".join(item["node"] for item in (state.get("trace") or []))
    facts = "\n".join(evidence["fact_lines"]) or "- （尚无已核对数字）"
    rag = "\n".join(f"- {line}" for line in evidence["rag_lines"]) or "- （尚无年报引用）"
    return (
        "【工作流暂停】数字与年报出处已核对，结论与工单尚未写入。\n\n"
        f"{state.get('year')} 年{evidence['label']}（事实库，未手算差额）：\n"
        f"{facts}\n\n管理层口径：\n{rag}\n\n"
        "【待写入草稿预览】（确认前不落库）\n"
        f"- 标题：{evidence['title']}\n"
        f"- 影响范围：{evidence['impact_scope']}\n"
        f"- 依据条款：{'；'.join(evidence['clause_refs']) or '（无）'}\n"
        f"- 结论：{evidence['conclusion_text']}\n\n"
        "回复「确认」写入 PENDING 审查工单，「取消」停止且不建草稿。"
        "检查点只保存本任务进度，不是聊天记忆；默认 24 小时过期。"
        f"\n轨迹：{path} → checkpoint"
    )


def conclude_node(state: ReviewState) -> dict[str, Any]:
    evidence = _draft_evidence(state)
    citations = evidence["citations"]
    clause_refs = evidence["clause_refs"]
    conclusion_text = evidence["conclusion_text"]
    if not clause_refs:
        return {
            "stop_reason": "结论缺少年报页码引用，停止。",
            "trace": [_step("conclude", tool="emit_conclusion", ok=False, detail="no_clause_refs")],
        }
    out = run_tool(
        "emit_conclusion",
        {
            "conclusion": conclusion_text[:500],
            "risk_level": "低",
            "clause_refs": clause_refs[:8],
            "evidence_quotes": [str(hit.get("snippet") or "")[:200] for hit in (state.get("rag_citations") or [])[:3]],
            "confidence": 0.72,
        },
        request_id=state.get("request_id"),
    )
    if not out.ok:
        reason = out.error or "结论未通过 Schema，停止，不提示凑过校验。"
        return {
            "stop_reason": reason,
            "reply": reason,
            "route": "agent_blocked",
            "trace": [_step("conclude", tool="emit_conclusion", ok=False)],
        }
    company_code = evidence.get("company_code")
    if not company_code:
        return {
            "stop_reason": "草稿缺少公司代码，停止，未写入工单。",
            "route": "agent_blocked",
            "trace": [_step("conclude", tool="create_review_draft", ok=False, detail="missing_company")],
        }
    draft = run_tool(
        "create_review_draft",
        {
            "company_code": company_code,
            "company_codes": evidence.get("company_codes") or [company_code],
            "title": evidence["title"][:120],
            "reason": evidence["reason"][:500],
            "conclusion": conclusion_text[:2000],
            "risk_level": "低",
            "clause_refs": clause_refs[:8],
            "evidence_quotes": [str(hit.get("snippet") or "")[:200] for hit in (state.get("rag_citations") or [])[:3]],
            "impact_scope": evidence["impact_scope"],
            "thread_id": state.get("thread_id"),
            "session_id": state.get("session_id"),
            "dept": state.get("dept") or "public",
        },
        request_id=state.get("request_id"),
        dept=state.get("dept"),
        idempotency_key=state.get("thread_id"),
    )
    if not draft.ok:
        reason = draft.error or "审查草稿写入失败，停止，未提交复核。"
        return {
            "stop_reason": reason,
            "reply": reason,
            "route": "agent_blocked",
            "trace": [_step("conclude", tool="create_review_draft", ok=False)],
        }
    draft_id = str((draft.result or {}).get("draft_id") or "")
    replayed = bool((draft.result or {}).get("replayed"))
    path = " → ".join(item["node"] for item in (state.get("trace") or []) + [_step("conclude")])
    written = "已存在" if replayed else "已写入"
    reply = (
        "【工作流】覆盖面 → 并列查数 → 核对 → 管理层检索 → 结论校验 → 工单草稿\n\n"
        f"{state['year']} 年{evidence['label']}（事实库，未手算差额）：\n"
        + "\n".join(evidence["fact_lines"])
        + "\n\n管理层口径：\n"
        + "\n".join(f"- {line}" for line in evidence["rag_lines"])
        + f"\n\n结论（已通过 Schema）：低风险；{conclusion_text}\n"
        f"\n{written} PENDING 审查工单 `{draft_id}`。"
        f"影响范围：{evidence['impact_scope']}。"
        "未提交 maker-checker，状态不会变为已复核。\n"
        f"\n轨迹：{path} → conclude"
    )
    return {
        "conclusion": out.result.get("conclusion") or {},
        "reply": reply,
        "route": "agent",
        "citations": citations,
        "rag_used": True,
        "draft_id": draft_id or None,
        "trace": [_step("conclude", tool="create_review_draft", ok=True, detail=draft_id)],
    }


def _budget_stop(thread_id: str | None, exc: BaseException) -> WorkflowResult:
    name = type(exc).__name__
    if "Recursion" in name or "recursion" in str(exc).lower():
        return WorkflowResult(
            route="agent_blocked",
            reply=budget_message("steps"),
            stop_reason="budget_exceeded",
            thread_id=thread_id,
            trace=[_step("stop", ok=False, detail="budget_exceeded:steps")],
        )
    raise exc


def stop_node(state: ReviewState) -> dict[str, Any]:
    if state.get("reply"):
        return {"trace": [_step("stop", ok=False)]}
    reason = state.get("stop_reason") or "已停止。"
    path = " → ".join(item["node"] for item in (state.get("trace") or []))
    return {
        "reply": f"{reason}\n轨迹：{path} → stop" if path else reason,
        "route": "agent_blocked",
        "rag_used": False,
        "trace": [_step("stop", ok=False, detail=reason)],
    }


def build_review_graph(checkpointer: BaseCheckpointSaver):
    graph = StateGraph(ReviewState)
    graph.add_node("classify", classify)
    graph.add_node("list_scope", list_scope_node)
    graph.add_node("compare", compare_node)
    graph.add_node("verify", verify_node)
    graph.add_node("rag", rag_node)
    graph.add_node("conclude", conclude_node)
    graph.add_node("stop", stop_node)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_after_classify, {"list_scope": "list_scope", "stop": "stop"})
    graph.add_conditional_edges("list_scope", route_after_scope, {"compare": "compare", "stop": "stop"})
    graph.add_conditional_edges("compare", route_after_compare, {"verify": "verify", "stop": "stop"})
    graph.add_conditional_edges("verify", route_after_verify, {"rag": "rag", "stop": "stop"})
    graph.add_conditional_edges("rag", route_after_rag, {"conclude": "conclude", "stop": "stop"})
    graph.add_edge("conclude", END)
    graph.add_edge("stop", END)
    return graph.compile(checkpointer=checkpointer, interrupt_before=["conclude"])


def review_graph(checkpointer: BaseCheckpointSaver | None = None):
    return build_review_graph(checkpointer or get_process_checkpointer())


def _to_citations(items: list[dict[str, Any]] | None) -> list[Citation]:
    citations: list[Citation] = []
    for item in items or []:
        if not item.get("doc_id"):
            continue
        citations.append(
            Citation(
                doc_id=str(item.get("doc_id") or ""),
                page=int(item.get("page") or 1),
                snippet=str(item.get("snippet") or ""),
                viewer_url=item.get("viewer_url"),
                title=item.get("title"),
                href=item.get("href"),
                kind=item.get("kind"),
            )
        )
    return citations


def _result_from_state(
    values: dict[str, Any],
    *,
    thread_id: str,
    pending_node: str | None = None,
    extra_trace: list[dict[str, Any]] | None = None,
) -> WorkflowResult:
    trace = list(values.get("trace") or [])
    if extra_trace:
        trace.extend(extra_trace)
    citations = values.get("citations") or []
    if pending_node == "conclude" and not citations:
        citations = _draft_evidence(values).get("citations") or []
    reply = str(values.get("reply") or values.get("stop_reason") or "已停止。")
    if pending_node == "conclude" and not values.get("reply"):
        reply = _pause_reply(values)
    route = "agent_paused" if pending_node == "conclude" else str(values.get("route") or "agent_blocked")
    pack = pack_from_workflow_values(values)
    reply, route, checked = apply_checked_reply(reply, pack, route=route)
    if pending_node == "conclude":
        route = "agent_paused"
    trace.append(checked.to_trace())
    return WorkflowResult(
        route=route,
        reply=reply,
        citations=_to_citations(citations),
        rag_used=bool(values.get("rag_used") or pending_node == "conclude"),
        trace=trace,
        stop_reason=values.get("stop_reason"),
        thread_id=thread_id,
        pending_node=pending_node,
        draft_id=values.get("draft_id"),
    )


def workflow_thread_status(
    thread_id: str | None,
    *,
    dept: str | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> str:
    if not thread_id:
        return "missing"
    if not thread_belongs_to_dept(thread_id, dept):
        return "forbidden"
    graph = review_graph(checkpointer)
    snapshot = graph.get_state(graph_config(thread_id))
    if not snapshot.values:
        return "missing"
    if checkpoint_expired(snapshot.created_at):
        graph.checkpointer.delete_thread(thread_id)
        return "expired"
    if snapshot.next == ("conclude",):
        return "paused"
    if snapshot.next:
        return "running"
    if snapshot.values.get("route") == "agent":
        return "done"
    return "stopped"


def run_review_workflow(
    question: str,
    *,
    session_id: str | None = None,
    request_id: str | None = None,
    thread_id: str | None = None,
    dept: str | None = None,
    action: Literal["start", "resume", "cancel"] = "start",
    checkpointer: BaseCheckpointSaver | None = None,
) -> WorkflowResult:
    if current_meter() is None:
        with use_limits():
            return _run_review_workflow(
                question,
                session_id=session_id,
                request_id=request_id,
                thread_id=thread_id,
                dept=dept,
                action=action,
                checkpointer=checkpointer,
            )
    return _run_review_workflow(
        question,
        session_id=session_id,
        request_id=request_id,
        thread_id=thread_id,
        dept=dept,
        action=action,
        checkpointer=checkpointer,
    )


def _run_review_workflow(
    question: str,
    *,
    session_id: str | None = None,
    request_id: str | None = None,
    thread_id: str | None = None,
    dept: str | None = None,
    action: Literal["start", "resume", "cancel"] = "start",
    checkpointer: BaseCheckpointSaver | None = None,
) -> WorkflowResult:
    graph = review_graph(checkpointer)
    if action in {"resume", "cancel"}:
        status = workflow_thread_status(thread_id, dept=dept, checkpointer=checkpointer)
        if status == "forbidden":
            return WorkflowResult(
                route="agent_blocked",
                reply="不能恢复其他部门的审查任务。",
                thread_id=thread_id,
                stop_reason="checkpoint_forbidden",
            )
        if status == "expired":
            return WorkflowResult(
                route="agent_blocked",
                reply="检查点已过期，请重新发起对比审查。",
                thread_id=thread_id,
                stop_reason="checkpoint_expired",
            )
        if status == "missing":
            return WorkflowResult(
                route="agent_blocked",
                reply="没有可恢复的审查检查点。",
                thread_id=thread_id,
                stop_reason="checkpoint_missing",
            )
        config = graph_config(thread_id or "")
        if action == "cancel":
            snapshot = graph.get_state(config)
            graph.checkpointer.delete_thread(thread_id)
            path = " → ".join(item["node"] for item in (snapshot.values.get("trace") or []))
            return WorkflowResult(
                route="agent_blocked",
                reply=f"已取消，未生成结论、未写入审查工单（emit_conclusion / create_review_draft 未执行）。\n轨迹：{path} → cancel" if path else "已取消，未生成结论、未写入审查工单。",
                trace=list(snapshot.values.get("trace") or []) + [_step("cancel", ok=False)],
                stop_reason="cancelled",
                thread_id=thread_id,
            )
        snapshot = graph.get_state(config)
        if snapshot.next == ("conclude",):
            try:
                raw = graph.invoke(None, config)
            except Exception as exc:
                return _budget_stop(thread_id, exc)
            snapshot = graph.get_state(config)
            values = snapshot.values or raw
            return _result_from_state(values, thread_id=thread_id or "")
        values = snapshot.values or {}
        return _result_from_state(values, thread_id=thread_id or "")

    thread_id = make_thread_id(dept)
    try:
        raw = graph.invoke(
            {
                "question": question,
                "session_id": session_id,
                "request_id": request_id,
                "thread_id": thread_id,
                "dept": normalize_dept(dept),
                "company_codes": [],
                "concept": None,
                "year": 2024,
                "scope": "consolidated",
                "lookups": [],
                "verifies": [],
                "rag_citations": [],
                "conclusion": None,
                "stop_reason": None,
                "reply": "",
                "route": "agent_blocked",
                "citations": [],
                "rag_used": False,
                "draft_id": None,
                "trace": [],
            },
            graph_config(thread_id),
        )
    except Exception as exc:
        return _budget_stop(thread_id, exc)
    snapshot = graph.get_state(graph_config(thread_id))
    values = snapshot.values or raw
    pending = snapshot.next[0] if snapshot.next else None
    extra = [_step("checkpoint", ok=True, detail="interrupt_before_conclude")] if pending == "conclude" else None
    return _result_from_state(values, thread_id=thread_id, pending_node=pending, extra_trace=extra)
