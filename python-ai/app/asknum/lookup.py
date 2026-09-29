"""受控问数：参数化查 fin_metric，不生成 SQL，不用 LLM 造数。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import psycopg

from app.asknum.citations import AsknumCite, append_markers, build_lookup_cites
from app.asknum.derived import DerivedNeed, DerivedPart, parse_derived_need
from app.asknum.pending import (
    clear_pending,
    is_topic_change,
    pending_hint,
    resolve_slots,
    save_pending,
)
from app.asknum.slots import (
    CONCEPT_LABELS,
    SCOPE_LABELS,
    AsknumSlots,
    company_display_name,
    concept_label,
    format_year_span,
    has_amount_intent,
    looks_like_metric_question,
    missing_slot_names,
    parse_slots,
)
from app.asknum.trace import AsknumTrace, save_asknum_trace
from app.db.connection import get_connection
from app.db.fin_metric_repository import (
    FinMetricRow,
    find_company_metrics,
    list_company_metric_years,
)

logger = logging.getLogger(__name__)

# 可查指标一览（反问时用）
_CONCEPT_HINT = "、".join(
    CONCEPT_LABELS[key]
    for key in (
        "revenue",
        "net_profit",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "operating_cash_flow",
        "eps",
    )
)


@dataclass(frozen=True)
class MetricLookup:
    """单次指标查询结果；只返回经过质量门校验的财务事实。"""

    company_code: str
    concept: str
    year: int
    scope: str
    outcome: str  # ok | human_review | missing | accepted_conflict | not_accepted
    row: FinMetricRow | None = None
    review_reason: str | None = None

    def to_trace_dict(self) -> dict:
        row = self.row
        value = None
        if self.outcome == "ok" and row is not None and row.value_yuan is not None:
            value = str(row.value_yuan)
        return {
            "company_code": self.company_code,
            "concept": self.concept,
            "year": self.year,
            "scope": self.scope,
            "outcome": self.outcome,
            "fact_key": row.fact_key if row else None,
            "doc_id": row.doc_id if row else None,
            "value_yuan": value,
            "review_reason": self.review_reason or (row.review_reason if row else None),
        }


@dataclass(frozen=True)
class AsknumResult:
    route: str
    reply: str
    slots: AsknumSlots | None = None
    lookups: tuple[MetricLookup, ...] = ()
    citations: tuple[AsknumCite, ...] = ()
    pending_request: dict | None = None
    intent: str | None = None


def _format_cny(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    text = f"{quantized:,.2f}"
    abs_val = abs(value)
    if abs_val >= Decimal("100000000"):
        yi = value / Decimal("100000000")
        return f"{text} 元（约 {yi:.2f} 亿元）"
    if abs_val >= Decimal("10000"):
        wan = value / Decimal("10000")
        return f"{text} 元（约 {wan:.2f} 万元）"
    return f"{text} 元"


_REVIEW_LABELS = {
    "critical_amount_mismatch": "交叉核对金额不一致",
}


def _clarify_reply(slots: AsknumSlots) -> str:
    scope = SCOPE_LABELS.get(slots.scope, slots.scope)
    missing = missing_slot_names(slots)
    year_text = format_year_span(slots.years)
    if "company" in missing and "metric" in missing:
        ask = "还需要指定公司和指标，例如比亚迪的营收或净利润。"
    elif "company" in missing:
        labels = "、".join(CONCEPT_LABELS.get(item, item) for item in slots.concepts)
        ask = f"要查「{labels}」，还需要指定公司，例如比亚迪或证券代码 002594。"
    else:
        names = "、".join(company_display_name(code) for code in slots.company_codes) or "该公司"
        ask = f"已识别公司「{names}」，还需要指定指标，例如营收或净利润。"
    if slots.year_defaulted:
        year_note = f"没写年份时按 {slots.year} 年{scope}。"
    else:
        year_note = f"已记录年份 {year_text}，口径按{scope}。"
    return (
        f"{ask}{year_note}"
        f"当前可查已入库直读指标：{_CONCEPT_HINT}。"
        "要核对比率或同比时请指定公司，查库后若组成科目不齐会说明数据不完整。"
    )


def _coverage_note(conn: psycopg.Connection | None, hit: MetricLookup) -> str:
    if conn is None:
        return ""
    try:
        years = list_company_metric_years(
            conn, company_code=hit.company_code, scope=hit.scope
        )
    except Exception:
        logger.debug("list_company_metric_years failed", exc_info=True)
        return ""
    if not years:
        return "该公司该口径尚未写入财务事实库。"
    if hit.year not in years:
        shown = "、".join(str(year) for year in years[:6])
        return f"该公司该口径已入库年份：{shown}，没有 {hit.year} 年。"
    return ""


def _pick_accepted(rows: list[FinMetricRow]) -> tuple[FinMetricRow | None, str | None]:
    """只采用 auto_accepted；多值冲突不静默挑选。"""
    accepted = [
        row
        for row in rows
        if row.status == "auto_accepted" and row.value_yuan is not None
    ]
    if accepted:
        values = {row.value_yuan for row in accepted}
        if len(values) > 1:
            return None, "accepted_conflict"
        return accepted[0], None

    review = [row for row in rows if row.status == "human_review"]
    if review:
        return None, "human_review"
    if rows:
        return None, "not_accepted"
    return None, "missing"


def lookup_metric(
    *,
    company_code: str,
    concept: str,
    year: int,
    scope: str = "consolidated",
    conn: psycopg.Connection | None = None,
) -> MetricLookup:
    """参数化查一条 fin_metric。W6 工具契约：只返回受控结果，不生成 SQL。"""

    def _query(connection: psycopg.Connection) -> list[FinMetricRow]:
        return find_company_metrics(
            connection,
            company_code=company_code,
            concept=concept,
            year=year,
            scope=scope,
        )

    if conn is not None:
        rows = _query(conn)
    else:
        with get_connection() as owned:
            rows = _query(owned)

    picked, reason = _pick_accepted(rows)
    if picked is not None:
        return MetricLookup(
            company_code=company_code,
            concept=concept,
            year=year,
            scope=scope,
            outcome="ok",
            row=picked,
        )
    sample = rows[0] if rows else None
    return MetricLookup(
        company_code=company_code,
        concept=concept,
        year=year,
        scope=scope,
        outcome=reason or "missing",
        row=sample,
        review_reason=sample.review_reason if sample else None,
    )


def lookup_metric_batch(
    *,
    company_codes: tuple[str, ...] | list[str],
    concepts: tuple[str, ...] | list[str],
    years: tuple[int, ...] | list[int],
    scope: str = "consolidated",
    conn: psycopg.Connection | None = None,
) -> tuple[MetricLookup, ...]:
    """公司 × 指标 × 年份逐条查库，不复用上一轮数字。"""

    def _run(connection: psycopg.Connection) -> tuple[MetricLookup, ...]:
        return tuple(
            lookup_metric(
                company_code=code,
                concept=concept,
                year=year,
                scope=scope,
                conn=connection,
            )
            for code in company_codes
            for concept in concepts
            for year in years
        )

    if conn is not None:
        return _run(conn)
    with get_connection() as owned:
        return _run(owned)


def _blocked_reply(
    hit: MetricLookup,
    slots: AsknumSlots,
    *,
    coverage_note: str = "",
) -> str:
    company = company_display_name(hit.company_code)
    raw_name = hit.row.raw_name if hit.row else None
    label = concept_label(hit.concept, raw_name)
    scope = SCOPE_LABELS.get(slots.scope, slots.scope)
    if hit.outcome == "human_review":
        detail = _REVIEW_LABELS.get(hit.review_reason or "", "待人工复核")
        return (
            f"{company}（{hit.company_code}）{hit.year} 年{scope}「{label}」已入库，"
            f"但{detail}，仍待人工复核，按质量门不返回该数字，也不会改用模型估算。"
            "点引用可打开财务事实库查看冲突明细。"
        )
    if hit.outcome == "accepted_conflict":
        return (
            f"{company}（{hit.company_code}）{hit.year} 年{scope}「{label}」存在多条自动通过记录且金额不一致，"
            "不静默挑选。请到「财务事实库」核对。"
        )
    if hit.outcome == "not_accepted":
        status = hit.row.status if hit.row else "unknown"
        return (
            f"{company}（{hit.company_code}）{hit.year} 年{scope}「{label}」记录状态为 {status}，"
            "未自动通过，不返回数字。"
        )
    extra = f"{coverage_note}" if coverage_note else ""
    return (
        f"财务事实库中没有 {company}（{hit.company_code}）{hit.year} 年{scope}"
        f"「{CONCEPT_LABELS.get(hit.concept, hit.concept)}」"
        f"的记录。{extra}"
        "未入库数字不会用模型估算；叙述类问题可改问合规问答检索年报。"
    )


def _success_line(row: FinMetricRow, slots: AsknumSlots, *, year: int, year_note: bool) -> str:
    company = company_display_name(row.company_code or "")
    code = row.company_code or ""
    label = concept_label(row.concept, row.raw_name)
    scope = SCOPE_LABELS.get(row.scope, row.scope)
    amount = _format_cny(row.value_yuan) if row.value_yuan is not None else "—"
    year_hint = "问题里没写年份，按 2024 年报。" if year_note else ""
    if row.concept == "eps":
        amount = f"{row.value_yuan} 元/股" if row.value_yuan is not None else "—"
    line = f"{company}（{code}）{year} 年{scope}「{label}」为 {amount}。"
    if year_hint:
        return f"{line}{year_hint}"
    return line


_OUTCOME_LABELS = {
    "ok": "已入库",
    "human_review": "已入库但待人工复核",
    "accepted_conflict": "已入库但金额冲突",
    "not_accepted": "已入库但未通过",
    "missing": "未入库",
}


def _part_status_line(part: DerivedPart, hit: MetricLookup | None, *, coverage: str) -> str:
    scope = SCOPE_LABELS.get(part.scope, part.scope)
    prefix = f"{part.label}（{part.year} 年{scope}）"
    if part.concept is None or hit is None:
        extra = coverage or "库中没有该科目或期间"
        return f"{prefix}：未入库。{extra}"
    status = _OUTCOME_LABELS.get(hit.outcome, hit.outcome)
    if hit.outcome == "ok":
        return f"{prefix}：{status}。"
    if hit.outcome == "human_review":
        detail = _REVIEW_LABELS.get(hit.review_reason or "", "待人工复核")
        return f"{prefix}：{status}（{detail}），不能用于计算。"
    if coverage:
        return f"{prefix}：{status}。{coverage}"
    return f"{prefix}：{status}。"


def _derived_incomplete_reply(
    *,
    slots: AsknumSlots,
    need: DerivedNeed,
    lines: list[str],
) -> str:
    who = "、".join(company_display_name(code) for code in slots.company_codes)
    return (
        f"要回答{who}的「{need.target_label}」，已按财务事实库核对组成科目：\n"
        + "\n".join(f"- {line}" for line in lines)
        + f"\n组成数据不完整，不能给出「{need.target_label}」，也不会用模型估算。"
    )


def _footer() -> str:
    return "数字来自财务事实库已通过记录；点金额旁引用可打开事实库或年报页。不从年报估算，不手算 ROE / 毛利率。"


def _session_uuid(session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        return str(UUID(session_id))
    except ValueError:
        return None


def _maybe_persist(
    *,
    question: str,
    slots: AsknumSlots,
    result: AsknumResult | None,
    persist_trace: bool,
    request_id: str | None,
    session_id: str | None,
    total_ms: float,
) -> None:
    if not persist_trace:
        return
    if result is None and not slots.concepts:
        return
    route = result.route if result is not None else "skip"
    lookups = [hit.to_trace_dict() for hit in (result.lookups if result else ())]
    save_asknum_trace(
        AsknumTrace(
            question=question,
            route=route,
            company_codes=list(slots.company_codes),
            concepts=list(slots.concepts),
            year=slots.year,
            year_defaulted=slots.year_defaulted,
            scope=slots.scope,
            narrative=slots.narrative,
            lookups=lookups,
            total_ms=total_ms,
            request_id=request_id,
            session_id=_session_uuid(session_id),
        )
    )


def _answer_derived(slots: AsknumSlots, need: DerivedNeed) -> AsknumResult:
    lookups: list[MetricLookup] = []
    lines: list[str] = []
    citations: list[AsknumCite] = []
    with get_connection() as conn:
        for code in slots.company_codes:
            for part in need.parts:
                hit: MetricLookup | None = None
                if part.concept:
                    hit = lookup_metric(
                        company_code=code,
                        concept=part.concept,
                        year=part.year,
                        scope=part.scope,
                        conn=conn,
                    )
                    lookups.append(hit)
                    cites = build_lookup_cites(
                        conn,
                        company_code=hit.company_code,
                        concept=hit.concept,
                        year=hit.year,
                        row=hit.row,
                        outcome=hit.outcome,
                        value_yuan=None,
                    )
                    coverage = _coverage_note(conn, hit)
                    line = _part_status_line(part, hit, coverage=coverage)
                    line = append_markers(line, len(citations) + 1, len(cites))
                    citations.extend(cites)
                elif "期间" in part.label:
                    line = _part_status_line(part, None, coverage="库中无季度或中报期间")
                else:
                    line = _part_status_line(part, None, coverage="未作为直读科目入库")
                if len(slots.company_codes) > 1:
                    line = f"{company_display_name(code)} {line}"
                lines.append(line)
    logger.info(
        "asknum derived kind=%s companies=%s parts=%d lookups=%d",
        need.kind,
        slots.company_codes,
        len(need.parts),
        len(lookups),
    )
    return AsknumResult(
        route="metric_blocked",
        reply=_derived_incomplete_reply(slots=slots, need=need, lines=lines),
        slots=slots,
        lookups=tuple(lookups),
        citations=tuple(citations),
    )


def _lookup_ready_result(slots: AsknumSlots, *, intent: str) -> AsknumResult:
    with get_connection() as conn:
        lookups = lookup_metric_batch(
            company_codes=slots.company_codes,
            concepts=slots.concepts,
            years=slots.years,
            scope=slots.scope,
            conn=conn,
        )
        lines: list[str] = []
        routes: list[str] = []
        citations: list[AsknumCite] = []
        for hit in lookups:
            cites = build_lookup_cites(
                conn,
                company_code=hit.company_code,
                concept=hit.concept,
                year=hit.year,
                row=hit.row,
                outcome=hit.outcome,
                value_yuan=hit.row.value_yuan if hit.row is not None else None,
            )
            mark_at = len(citations) + 1
            if hit.outcome == "ok" and hit.row is not None:
                routes.append("metric")
                line = _success_line(
                    hit.row,
                    slots,
                    year=hit.year,
                    year_note=slots.year_defaulted,
                )
            else:
                routes.append("metric_blocked")
                line = _blocked_reply(
                    hit,
                    slots,
                    coverage_note=_coverage_note(conn, hit),
                )
            lines.append(append_markers(line, mark_at, len(cites)))
            citations.extend(cites)
    route = "metric" if all(item == "metric" for item in routes) else "metric_blocked"
    if len(lines) == 1:
        reply = lines[0] if route != "metric" else f"{lines[0]}\n{_footer()}"
    else:
        bullets = "\n".join(f"- {line}" for line in lines)
        head = "按财务事实库逐条查询（不手算对比比率）："
        reply = f"{head}\n{bullets}"
        if route == "metric":
            reply = f"{reply}\n{_footer()}"
    logger.info(
        "asknum route=%s companies=%s concepts=%s years=%s cites=%d",
        route,
        slots.company_codes,
        slots.concepts,
        slots.years,
        len(citations),
    )
    return AsknumResult(
        route=route,
        reply=reply,
        slots=slots,
        lookups=lookups,
        citations=tuple(citations),
        intent=intent,
    )


def _attach_pending(
    result: AsknumResult,
    *,
    session_id: str | None,
    intent: str,
) -> AsknumResult:
    slots = result.slots
    if slots is None:
        return result
    if result.route == "metric_clarify":
        pending = save_pending(session_id, slots, intent=intent)
        payload = pending.to_ui() if pending is not None else {
            "intent": intent,
            "company": slots.company_codes[0] if slots.company_codes else None,
            "years": list(slots.years),
            "metric": slots.concepts[0] if slots.concepts else None,
            "scope": slots.scope,
            "missing": missing_slot_names(slots),
            "hint": pending_hint(slots),
        }
        return AsknumResult(
            route=result.route,
            reply=result.reply,
            slots=slots,
            lookups=result.lookups,
            citations=result.citations,
            pending_request=payload,
            intent=intent,
        )
    clear_pending(session_id)
    return AsknumResult(
        route=result.route,
        reply=result.reply,
        slots=slots,
        lookups=result.lookups,
        citations=result.citations,
        pending_request=None,
        intent=intent,
    )


def try_answer(
    question: str,
    *,
    persist_trace: bool = True,
    request_id: str | None = None,
    session_id: str | None = None,
    slots: AsknumSlots | None = None,
) -> AsknumResult | None:
    """能抽出标准指标且非叙述题则拦截；否则返回 None 交给 RAG / 寒暄。"""
    started = time.perf_counter()
    incoming = slots or parse_slots(question)
    slots, intent, prior = resolve_slots(
        question,
        session_id=session_id,
        incoming=incoming,
    )
    merged = prior is not None and slots is not incoming
    result: AsknumResult | None = None

    if is_topic_change(question):
        result = None
    else:
        derived = parse_derived_need(question, slots)
        if slots.narrative:
            result = None
        elif derived is not None:
            if not slots.company_codes:
                result = AsknumResult(
                    route="metric_clarify",
                    reply=_clarify_reply(slots),
                    slots=slots,
                    intent=intent,
                )
            else:
                result = _answer_derived(slots, derived)
        elif not slots.concepts:
            if merged or (
                looks_like_metric_question(question)
                and (slots.company_codes or has_amount_intent(question))
            ):
                logger.info("asknum clarify missing-concept companies=%s", slots.company_codes)
                result = AsknumResult(
                    route="metric_clarify",
                    reply=_clarify_reply(slots),
                    slots=slots,
                    intent=intent,
                )
            else:
                result = None
        elif not slots.company_codes:
            logger.info("asknum clarify concepts=%s", slots.concepts)
            result = AsknumResult(
                route="metric_clarify",
                reply=_clarify_reply(slots),
                slots=slots,
                intent=intent,
            )
        else:
            result = _lookup_ready_result(slots, intent=intent)

    if result is not None:
        result = _attach_pending(result, session_id=session_id, intent=intent)
    elif prior is None:
        clear_pending(session_id)

    _maybe_persist(
        question=question,
        slots=slots,
        result=result,
        persist_trace=persist_trace,
        request_id=request_id,
        session_id=session_id,
        total_ms=(time.perf_counter() - started) * 1000,
    )
    return result
