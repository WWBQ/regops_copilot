"""点名才进的 Function Calling：模型选只读工具，数字仍只认工具返回。"""

from __future__ import annotations

import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from contextlib import nullcontext

from app.agents.budget import budget_message, classify_error, current_limits, current_meter, use_limits
from app.agents.evidence import apply_checked_reply, pack_from_tool_trace
from app.asknum.citations import facts_href
from app.asknum.slots import CONCEPT_LABELS, company_display_name
from app.models.base import ChatResult, LLMClient, ToolCallRequest
from app.prompts.library import render_system
from app.schemas.chat import Citation
from app.schemas.tools import ToolContext, ToolInvokeResponse
from app.tools.registry import invoke_tool, openai_tool_schemas

logger = logging.getLogger(__name__)

ALLOWED_TOOLS = (
    "list_scope",
    "lookup_metric",
    "compare_peers",
    "verify_number",
    "rag_search",
)
MAX_ROUNDS = 4
MAX_TOOL_CALLS = 6
MAX_LOOKUP_METRIC = 1
ToolEvent = Callable[[str, dict[str, Any]], Awaitable[None] | None]
_TOOL_STATUS = {
    "list_scope": "正在查看可查范围…",
    "lookup_metric": "正在查询财务数字…",
    "compare_peers": "正在并列同业数字…",
    "verify_number": "正在核对金额…",
    "rag_search": "正在检索年报…",
}
def _tool_loop_system() -> str:
    return render_system("tools.loop")


@dataclass
class ToolLoopResult:
    route: str
    reply: str
    citations: list[Citation] = field(default_factory=list)
    rag_used: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    trace: list[dict[str, Any]] = field(default_factory=list)


def _openai_tools() -> list[dict[str, Any]]:
    allowed = set(ALLOWED_TOOLS)
    return [item for item in openai_tool_schemas() if item.get("function", {}).get("name") in allowed]


def _assistant_tool_message(result: ChatResult) -> dict[str, Any]:
    calls = []
    for item in result.tool_calls:
        calls.append(
            {
                "id": item.id or item.name,
                "type": "function",
                "function": {
                    "name": item.name,
                    "arguments": json.dumps(item.arguments, ensure_ascii=False),
                },
            }
        )
    return {
        "role": "assistant",
        "content": result.content or None,
        "tool_calls": calls,
    }


def _citations_from_lookup(row: dict[str, Any]) -> Citation | None:
    code = str(row.get("company_code") or "")
    concept = str(row.get("concept") or "")
    if not code:
        return None
    name = company_display_name(code)
    label = CONCEPT_LABELS.get(concept, concept or "指标")
    amount = row.get("value_yuan")
    snippet = f"{name} {label} {amount}" if amount else f"{name} {label}"
    return Citation(
        doc_id=str(row.get("doc_id") or f"{code}_{row.get('year') or ''}"),
        page=1,
        snippet=snippet,
        title=f"财务事实库 · {name} {label}",
        href=facts_href(company_code=code, concept=concept or None, status=row.get("status")),
        kind="facts",
    )


def _citations_from_tool(name: str, payload: dict[str, Any]) -> list[Citation]:
    citations: list[Citation] = []
    if name == "lookup_metric":
        if payload.get("lookups"):
            for row in payload.get("lookups") or []:
                if isinstance(row, dict) and row.get("ok"):
                    item = _citations_from_lookup(row)
                    if item:
                        citations.append(item)
        elif payload.get("ok"):
            item = _citations_from_lookup(payload)
            if item:
                citations.append(item)
    elif name == "compare_peers":
        for row in payload.get("lookups") or []:
            if isinstance(row, dict) and row.get("ok"):
                item = _citations_from_lookup(row)
                if item:
                    citations.append(item)
    elif name == "rag_search":
        seen: set[tuple[str, int]] = set()
        for hit in payload.get("citations") or []:
            if not isinstance(hit, dict) or not hit.get("doc_id") or int(hit.get("page") or 0) < 1:
                continue
            page = int(hit["page"])
            key = (str(hit["doc_id"]), page)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                Citation(
                    doc_id=str(hit["doc_id"]),
                    page=page,
                    snippet=str(hit.get("snippet") or ""),
                    title=hit.get("title"),
                    viewer_url=hit.get("viewer_url"),
                    kind="document",
                )
            )
            if len(seen) >= 3:
                break
    return citations


def _run_one_tool(
    call: ToolCallRequest,
    *,
    session_id: str | None,
    request_id: str | None,
) -> ToolInvokeResponse:
    if call.name not in ALLOWED_TOOLS:
        return ToolInvokeResponse(
            name=call.name,
            ok=False,
            stop=True,
            result={},
            error=f"工具 {call.name} 不在本场景白名单，只读：{', '.join(ALLOWED_TOOLS)}。",
            error_code="unknown_tool",
            request_id=request_id,
        )
    arguments = dict(call.arguments)
    if call.name == "rag_search" and session_id and not arguments.get("session_id"):
        arguments["session_id"] = session_id
    out = invoke_tool(call.name, arguments, context=ToolContext(request_id=request_id))
    message = classify_error(out)
    if message and out.error != message:
        return out.model_copy(update={"error": message})
    return out


def _executed(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in trace if not item.get("skipped")]


def _lookup_count(trace: list[dict[str, Any]]) -> int:
    return sum(1 for item in _executed(trace) if item["name"] == "lookup_metric")


_NARRATIVE_OVERVIEW_RE = re.compile(
    r"(?:经营|业绩|财务)(?:得?怎么样|如何|情况|状况)|整体(?:情况|怎么样)"
)
_SCOPE_QUESTION_RE = re.compile(r"有哪些可查|能查什么|可查指标|库里有什么")


def _has_tool(trace: list[dict[str, Any]], name: str) -> bool:
    return any(item["name"] == name for item in _executed(trace))


def _needs_overview_rag(question: str, trace: list[dict[str, Any]]) -> bool:
    if _has_tool(trace, "rag_search") or _over_budget(trace, "rag_search"):
        return False
    text = question or ""
    if _SCOPE_QUESTION_RE.search(text):
        return False
    return bool(_NARRATIVE_OVERVIEW_RE.search(text))


def _record_tool(
    trace: list[dict[str, Any]],
    citations: list[Citation],
    out: ToolInvokeResponse,
) -> bool:
    payload = out.result if isinstance(out.result, dict) else {}
    citations.extend(_citations_from_tool(out.name, payload))
    rag_hit = out.name == "rag_search" and out.ok
    entry: dict[str, Any] = {
        "name": out.name,
        "ok": out.ok,
        "stop": out.stop,
        "error": out.error,
    }
    if payload.get("value_yuan"):
        entry["value_yuan"] = payload["value_yuan"]
    lookups = [
        {"value_yuan": row.get("value_yuan")}
        for row in payload.get("lookups") or []
        if isinstance(row, dict) and row.get("value_yuan")
    ]
    if lookups:
        entry["lookups"] = lookups
    trace.append(entry)
    if out.stop and not out.ok:
        logger.info("tool_loop stop name=%s error=%s", out.name, out.error)
    return rag_hit


def _force_overview_rag(
    question: str,
    *,
    session_id: str | None,
    request_id: str | None,
    messages: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    citations: list[Citation],
) -> bool:
    call = ToolCallRequest(id="forced_rag", name="rag_search", arguments={"question": question})
    out = _run_one_tool(call, session_id=session_id, request_id=request_id)
    rag_hit = _record_tool(trace, citations, out)
    payload = json.dumps(out.model_dump(), ensure_ascii=False)
    messages.append(
        {
            "role": "system",
            "content": (
                "经营概况不能只列已查数字。已代为 rag_search 年报管理层概述。"
                "请综合已核对数字与下列检索结果作答；叙述须标明非已核对数字；句末 [n]，不要写 doc_id。\n"
                + payload[:4000]
            ),
        }
    )
    return rag_hit


def _over_budget(trace: list[dict[str, Any]], name: str | None = None) -> bool:
    limits = current_limits()
    meter = current_meter()
    if meter is not None:
        kind = meter.reject_loop_tool(name or "")
        if kind:
            return True
    if len(_executed(trace)) >= limits.loop_max_tool_calls:
        return True
    if name == "lookup_metric" and _lookup_count(trace) >= limits.max_lookup_metric:
        return True
    return False


def _skip_response(call: ToolCallRequest, reason: str, request_id: str | None) -> ToolInvokeResponse:
    return ToolInvokeResponse(
        name=call.name,
        ok=False,
        stop=False,
        result={},
        error=reason,
        request_id=request_id,
    )


def _dedupe_citations(items: list[Citation]) -> list[Citation]:
    seen: set[tuple[str, str, str, int, str]] = set()
    out: list[Citation] = []
    for item in items:
        key = (item.kind or "", item.href or "", item.doc_id, item.page, (item.snippet or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _amount_from_facts(cite: Citation) -> Decimal | None:
    token = (cite.snippet or "").strip().split()[-1] if cite.snippet else ""
    try:
        return Decimal(token)
    except (InvalidOperation, ValueError):
        return None


def _plain_decimal(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".")


def _grouped_decimal(plain: str) -> str:
    sign = ""
    if plain.startswith("-"):
        sign = "-"
        plain = plain[1:]
    if "." in plain:
        integer, frac = plain.split(".", 1)
        return f"{sign}{int(integer):,}.{frac}"
    return f"{sign}{int(plain):,}"


def _amount_needles(amount: Decimal) -> list[str]:
    compact = _plain_decimal(amount)
    grouped = _grouped_decimal(compact)
    needles: list[str] = []
    if grouped != compact:
        needles.append(grouped)
    if abs(amount) >= 100:
        needles.append(compact)
    yi = (amount / Decimal("100000000")).quantize(Decimal("0.01"))
    if abs(yi) >= Decimal("0.01"):
        yi_text = format(yi, "f")
        yi_grouped = _grouped_decimal(yi_text)
        for item in (yi_grouped, yi_text):
            needles.append(f"{item} 亿元")
            needles.append(f"{item}亿元")
            needles.append(item)
    elif abs(amount) >= 1:
        needles.append(compact)
    return needles


def _cite_needles(cite: Citation) -> list[str]:
    if cite.kind == "facts":
        amount = _amount_from_facts(cite)
        return _amount_needles(amount) if amount is not None else []
    needles: list[str] = []
    if cite.page:
        needles.append(f"第{cite.page}页")
        needles.append(f"第 {cite.page} 页")
    for token in re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", cite.snippet or ""):
        needles.append(token)
    return needles


def _already_marked(text: str, at: int) -> bool:
    return bool(re.match(r"\s*\[\d{1,2}\]", text[at : at + 8]))


def _insert_after(text: str, needle: str, mark: str) -> str | None:
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            return None
        end = index + len(needle)
        if not _already_marked(text, end):
            return text[:end] + mark + text[end:]
        start = end


def _place_mark(text: str, mark: str, cite: Citation) -> str | None:
    if cite.kind != "facts" and cite.doc_id and cite.page:
        paren = re.search(
            rf"[（(][^）)]*{re.escape(cite.doc_id)}[^）)]*第\s*{cite.page}\s*页[^）)]*[）)]",
            text,
        )
        if paren:
            return text[: paren.start()] + mark + text[paren.end() :]
    for needle in _cite_needles(cite):
        placed = _insert_after(text, needle, mark)
        if placed is not None:
            return placed
    return None


_FOOTER_RE = re.compile(r"\n*出处：(?:\[\d{1,2}\])+\s*$")


def _strip_cite_footer(text: str) -> str:
    return _FOOTER_RE.sub("", text or "").rstrip()


def _compact_citation_marks(text: str, citations: list[Citation]) -> tuple[str, list[Citation]]:
    remap: dict[int, int] = {}
    kept: list[Citation] = []

    def repl(match: re.Match[str]) -> str:
        old = int(match.group(1))
        index = old - 1
        if index < 0 or index >= len(citations):
            return match.group(0)
        if old not in remap:
            remap[old] = len(kept) + 1
            kept.append(citations[index])
        return f"[{remap[old]}]"

    return re.sub(r"\[(\d{1,2})\]", repl, text), kept


def _bind_citations(text: str, citations: list[Citation]) -> tuple[str, list[Citation]]:
    text = _strip_cite_footer(text)
    if not citations:
        return text, []
    used: set[int] = set()
    for match in re.finditer(r"\[(\d{1,2})\]", text):
        index = int(match.group(1)) - 1
        if 0 <= index < len(citations):
            used.add(index)
    for index, cite in enumerate(citations):
        if index in used:
            continue
        placed = _place_mark(text, f"[{index + 1}]", cite)
        if placed is None:
            continue
        text = placed
        used.add(index)
    return _compact_citation_marks(text, citations)


def _citation_guide(citations: list[Citation]) -> str:
    lines = ["用到的数字或年报叙述在句末写 [n]，不要写 doc_id，不要在文末列出处。"]
    for index, cite in enumerate(citations, start=1):
        if cite.kind == "facts":
            lines.append(f"[{index}] {cite.title or cite.snippet}")
        else:
            snippet = (cite.snippet or "").replace("\n", " ").strip()[:60]
            lines.append(f"[{index}] 年报第{cite.page}页 {snippet}")
    return "\n".join(lines)


def _format_path(trace: list[dict[str, Any]]) -> str:
    names: list[tuple[str, int]] = []
    for item in _executed(trace):
        name = item["name"]
        if names and names[-1][0] == name:
            names[-1] = (name, names[-1][1] + 1)
        else:
            names.append((name, 1))
    return " → ".join(f"{name}×{count}" if count > 1 else name for name, count in names) or "（模型未调用工具）"


def _format_reply(text: str, trace: list[dict[str, Any]], citations: list[Citation] | None = None) -> tuple[str, list[Citation]]:
    body = (text or "").strip() or "已停止。未补造数字。"
    body, bound = _bind_citations(body, citations or [])
    return f"【工具自选】{_format_path(trace)}\n\n{body}", bound


async def _emit(on_event: ToolEvent | None, kind: str, payload: dict[str, Any]) -> None:
    if on_event is None:
        return
    maybe = on_event(kind, payload)
    if inspect.isawaitable(maybe):
        await maybe


async def run_tool_loop(
    question: str,
    client: LLMClient,
    *,
    session_id: str | None = None,
    request_id: str | None = None,
    temperature: float = 0.1,
    on_event: ToolEvent | None = None,
) -> ToolLoopResult:
    context = use_limits() if current_meter() is None else nullcontext(current_meter())
    with context as meter:
        return await _run_tool_loop(
            question,
            client,
            session_id=session_id,
            request_id=request_id,
            temperature=temperature,
            on_event=on_event,
            meter=meter,
        )


async def _run_tool_loop(
    question: str,
    client: LLMClient,
    *,
    session_id: str | None = None,
    request_id: str | None = None,
    temperature: float = 0.1,
    on_event: ToolEvent | None = None,
    meter=None,
) -> ToolLoopResult:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _tool_loop_system()},
        {"role": "user", "content": question},
    ]
    tools = _openai_tools()
    trace: list[dict[str, Any]] = []
    citations: list[Citation] = []
    prompt_tokens = 0
    completion_tokens = 0
    latency_ms = 0.0
    final_text = ""
    rag_used = False
    limits = current_limits()
    await _emit(on_event, "status", {"text": "正在选择工具…"})

    for _round in range(limits.max_rounds):
        if meter is not None:
            kind = meter.reject_round()
            if kind:
                final_text = budget_message(kind)
                break
            meter.note_round()
        tool_schemas = None if _over_budget(trace) else tools
        result = await client.chat_with_usage(messages, temperature=temperature, tools=tool_schemas)
        prompt_tokens += result.prompt_tokens
        completion_tokens += result.completion_tokens
        latency_ms += result.latency_ms
        if meter is not None:
            meter.note_tokens(result.prompt_tokens, result.completion_tokens)
        if not result.tool_calls:
            if _needs_overview_rag(question, trace):
                if result.content:
                    messages.append({"role": "assistant", "content": result.content})
                await _emit(on_event, "status", {"text": "正在检索年报…"})
                if _force_overview_rag(
                    question,
                    session_id=session_id,
                    request_id=request_id,
                    messages=messages,
                    trace=trace,
                    citations=citations,
                ):
                    rag_used = True
                continue
            final_text = result.content
            break
        messages.append(_assistant_tool_message(result))
        for call in result.tool_calls:
            if _over_budget(trace, call.name):
                limits = current_limits()
                reason = (
                    f"工具预算已满（最多 {limits.loop_max_tool_calls} 次调用；"
                    f"lookup_metric {limits.max_lookup_metric} 次，科目放进 concepts 列表）。"
                    "请根据已返回结果作答，不要再逐条查 list_scope 里的全部科目。"
                )
                out = _skip_response(call, reason, request_id)
                trace.append(
                    {
                        "name": call.name,
                        "ok": False,
                        "stop": False,
                        "error": reason,
                        "skipped": True,
                    }
                )
            else:
                await _emit(
                    on_event,
                    "status",
                    {"text": _TOOL_STATUS.get(call.name, f"正在调用 {call.name}…")},
                )
                out = _run_one_tool(call, session_id=session_id, request_id=request_id)
                if meter is not None:
                    meter.note_tool(call.name)
                if _record_tool(trace, citations, out):
                    rag_used = True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id or call.name,
                    "content": json.dumps(out.model_dump(), ensure_ascii=False),
                }
            )
        bound_so_far = _dedupe_citations(citations)
        if bound_so_far:
            messages.append({"role": "system", "content": _citation_guide(bound_so_far)})
        if _over_budget(trace):
            messages.append(
                {
                    "role": "system",
                    "content": "工具预算已满。只根据已有工具结果作答，不得补充数字，不要再调用工具，不要在文末列出处。",
                }
            )
        elif _lookup_count(trace) >= limits.max_lookup_metric:
            messages.append(
                {
                    "role": "system",
                    "content": "查数已完成。不要再逐条 lookup。经营概况必须 rag_search 一次管理层讨论，再综合作答，不要现在只列数字。",
                }
            )
    else:
        await _emit(on_event, "status", {"text": "正在生成回答…"})
        wrap = await client.chat_with_usage(
            messages
            + [
                {
                    "role": "system",
                    "content": "已达工具步数上限。只根据已返回的工具结果作答，不得补充数字。句末用 [n] 角标，不要在文末列出处。",
                }
            ],
            temperature=temperature,
        )
        prompt_tokens += wrap.prompt_tokens
        completion_tokens += wrap.completion_tokens
        latency_ms += wrap.latency_ms
        if meter is not None:
            meter.note_tokens(wrap.prompt_tokens, wrap.completion_tokens)
        final_text = wrap.content or "已达工具步数上限，停止。未补造数字。"

    if final_text.startswith("超过") and "预算" in final_text:
        route = "tools_blocked"
        citations = _dedupe_citations(citations)
        reply = f"【工具自选】{_format_path(trace)}\n\n{final_text}"
        pack = pack_from_tool_trace(trace, citations)
        reply, route, checked = apply_checked_reply(reply, pack, route=route)
        trace.append(checked.to_trace())
        return ToolLoopResult(
            route=route,
            reply=reply,
            citations=citations,
            rag_used=rag_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            trace=trace,
        )

    route = "tools_blocked" if any(item.get("ok") is False and item.get("stop") for item in trace) and not final_text.strip() else "tools"
    if not final_text.strip() and any(item.get("ok") is False for item in trace):
        route = "tools_blocked"
        final_text = next((item.get("error") for item in trace if item.get("error")), "") or final_text
    citations = _dedupe_citations(citations)
    reply, citations = _format_reply(final_text, trace, citations)
    pack = pack_from_tool_trace(trace, citations)
    reply, route, checked = apply_checked_reply(reply, pack, route=route)
    trace.append(checked.to_trace())
    return ToolLoopResult(
        route=route,
        reply=reply,
        citations=citations,
        rag_used=rag_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        trace=trace,
    )
