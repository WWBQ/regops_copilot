"""w5-2：Python Mock 工具。固定响应 + 异常注入，不连 Java / 不连库。"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.documents.titles import COMPANY_DISPLAY_NAMES
from app.schemas.tools import (
    ComparePeersArgs,
    EmitConclusionArgs,
    ListScopeArgs,
    LookupMetricArgs,
    ToolContext,
    ToolInvokeResponse,
    VerifyNumberArgs,
)
from app.tools.verify import _same_amount, parse_claimed_yuan

# research 只能看整车两家；compliance 看五家金样本
DEPT_ALLOW: dict[str, frozenset[str]] = {
    "research": frozenset({"002594", "601633"}),
    "compliance": frozenset({"002594", "601633", "000333", "000651", "600031"}),
}

_LOOKUP: dict[tuple[str, str, int, str], dict[str, Any]] = {
    ("002594", "revenue", 2024, "consolidated"): {
        "value_yuan": "777102455000",
        "raw_name": "营业总收入",
        "status": "auto_accepted",
        "doc_id": "002594_2024",
        "fact_key": "revenue|2024-12-31|consolidated|CNY|income",
    },
    ("002594", "net_profit", 2024, "consolidated"): {
        "value_yuan": "41587940000",
        "raw_name": "净利润",
        "status": "auto_accepted",
        "doc_id": "002594_2024",
        "fact_key": "net_profit|2024-12-31|consolidated|CNY|income",
    },
    ("601633", "net_profit", 2024, "consolidated"): {
        "value_yuan": "12660012515.78",
        "raw_name": "净利润",
        "status": "auto_accepted",
        "doc_id": "601633_2024",
        "fact_key": "net_profit|2024-12-31|consolidated|CNY|income",
    },
}

_SCOPE_ROWS: list[tuple[str, int, str, str]] = [
    ("002594", 2024, "consolidated", "revenue"),
    ("002594", 2024, "consolidated", "net_profit"),
    ("601633", 2024, "consolidated", "net_profit"),
]

_IDEMPOTENCY: dict[tuple[str, str], ToolInvokeResponse] = {}


def clear_mock_state() -> None:
    _IDEMPOTENCY.clear()


def _fail(
    name: str,
    *,
    error_code: str,
    message: str,
    request_id: str | None,
    result: dict[str, Any] | None = None,
) -> ToolInvokeResponse:
    return ToolInvokeResponse(
        name=name,
        ok=False,
        stop=True,
        result=result or {},
        error=message,
        error_code=error_code,  # type: ignore[arg-type]
        request_id=request_id,
    )


def _companies_from_args(parsed: BaseModel) -> list[str]:
    codes = getattr(parsed, "company_codes", None)
    if codes:
        return list(codes)
    single = getattr(parsed, "company_code", None)
    return [single] if single else []


def _check_acl(name: str, parsed: BaseModel, ctx: ToolContext) -> ToolInvokeResponse | None:
    if ctx.inject == "unauthorized":
        return _fail(
            name,
            error_code="unauthorized",
            message="越权：注入 unauthorized。",
            request_id=ctx.request_id,
        )
    dept = ctx.dept
    if not dept:
        return None
    allow = DEPT_ALLOW.get(dept)
    if allow is None:
        return _fail(
            name,
            error_code="unauthorized",
            message=f"未知部门 {dept}。",
            request_id=ctx.request_id,
        )
    for company in _companies_from_args(parsed):
        if company not in allow:
            return _fail(
                name,
                error_code="unauthorized",
                message=f"部门 {dept} 不能查询 {company}。",
                request_id=ctx.request_id,
            )
    return None


def _lookup(args: LookupMetricArgs, ctx: ToolContext) -> ToolInvokeResponse:
    key = (args.company_code, args.concept, args.year, args.scope)
    row = _LOOKUP.get(key)
    if ctx.inject == "missing" or row is None:
        return _fail(
            "lookup_metric",
            error_code="missing",
            message=f"{args.company_code} {args.year} {args.concept} 无数据。",
            request_id=ctx.request_id,
            result={
                "ok": False,
                "stop": True,
                "outcome": "missing",
                "company_code": args.company_code,
                "concept": args.concept,
                "year": args.year,
                "scope": args.scope,
                "value_yuan": None,
                "message": "Mock：无数据。",
            },
        )
    return ToolInvokeResponse(
        name="lookup_metric",
        ok=True,
        stop=False,
        result={
            "ok": True,
            "stop": False,
            "outcome": "ok",
            "company_code": args.company_code,
            "concept": args.concept,
            "year": args.year,
            "scope": args.scope,
            "value_yuan": row["value_yuan"],
            "raw_name": row["raw_name"],
            "fact_key": row["fact_key"],
            "doc_id": row["doc_id"],
            "status": row["status"],
            "review_reason": None,
            "message": "Mock：已命中固定响应。",
        },
        request_id=ctx.request_id,
    )


def _list_scope(args: ListScopeArgs, ctx: ToolContext) -> ToolInvokeResponse:
    if ctx.inject == "missing":
        return _fail(
            "list_scope",
            error_code="missing",
            message="Mock：覆盖面无数据。",
            request_id=ctx.request_id,
            result={"ok": True, "stop": False, "companies": [], "years": [], "items": [], "message": "无数据"},
        )
    allow = DEPT_ALLOW.get(ctx.dept) if ctx.dept else None
    rows = []
    for company, year, scope, concept in _SCOPE_ROWS:
        if args.company_code and company != args.company_code:
            continue
        if args.year is not None and year != args.year:
            continue
        if args.scope and scope != args.scope:
            continue
        if allow is not None and company not in allow:
            continue
        rows.append((company, year, scope, concept))
    grouped: dict[tuple[str, int, str], list[str]] = {}
    for company, year, scope, concept in rows:
        grouped.setdefault((company, year, scope), []).append(concept)
    items = [
        {
            "company_code": company,
            "company_name": COMPANY_DISPLAY_NAMES.get(company, company),
            "year": year,
            "scope": scope,
            "concepts": concepts,
        }
        for (company, year, scope), concepts in grouped.items()
    ]
    companies = sorted({item["company_code"] for item in items})
    years = sorted({item["year"] for item in items}, reverse=True)
    return ToolInvokeResponse(
        name="list_scope",
        ok=True,
        stop=False,
        result={
            "ok": True,
            "stop": False,
            "companies": companies,
            "years": years,
            "items": items,
            "message": f"Mock：{len(items)} 组口径。",
        },
        request_id=ctx.request_id,
    )


def _verify(args: VerifyNumberArgs, ctx: ToolContext) -> ToolInvokeResponse:
    lookup = _lookup(
        LookupMetricArgs(
            company_code=args.company_code,
            concept=args.concept,
            year=args.year,
            scope=args.scope,
        ),
        ctx,
    )
    if not lookup.ok:
        lookup.name = "verify_number"
        lookup.result = {
            "ok": False,
            "stop": True,
            "verdict": "unavailable",
            "lookup_outcome": lookup.result.get("outcome", "missing"),
            "claimed_yuan": None,
            "fact_yuan": None,
            "message": f"无法核对：{lookup.error}",
        }
        return lookup
    claimed = parse_claimed_yuan(args.claimed)
    fact = Decimal(lookup.result["value_yuan"])
    matched = _same_amount(claimed, fact)
    return ToolInvokeResponse(
        name="verify_number",
        ok=matched,
        stop=not matched,
        result={
            "ok": matched,
            "stop": not matched,
            "verdict": "match" if matched else "mismatch",
            "lookup_outcome": "ok",
            "claimed_yuan": format(claimed, "f"),
            "fact_yuan": lookup.result["value_yuan"],
            "message": "Mock：金额一致。" if matched else "Mock：金额不一致。",
        },
        request_id=ctx.request_id,
    )


def mock_invoke(name: str, parsed: BaseModel, ctx: ToolContext) -> ToolInvokeResponse:
    if ctx.inject == "timeout":
        return _fail(
            name,
            error_code="timeout",
            message="Mock：后端超时（未真实等待）。",
            request_id=ctx.request_id,
        )
    denied = _check_acl(name, parsed, ctx)
    if denied is not None:
        return denied
    if name == "lookup_metric":
        args = parsed
        names = list(getattr(args, "concepts", None) or [getattr(args, "concept", None)])
        names = [item for item in names if item]
        if len(names) <= 1:
            return _lookup(
                LookupMetricArgs(
                    company_code=args.company_code,  # type: ignore[attr-defined]
                    concept=names[0],
                    year=args.year,  # type: ignore[attr-defined]
                    scope=args.scope,  # type: ignore[attr-defined]
                ),
                ctx,
            )
        lookups = []
        usable = False
        for concept in names:
            one = _lookup(
                LookupMetricArgs(
                    company_code=args.company_code,  # type: ignore[attr-defined]
                    concept=concept,
                    year=args.year,  # type: ignore[attr-defined]
                    scope=args.scope,  # type: ignore[attr-defined]
                ),
                ctx,
            )
            lookups.append(one.result)
            usable = usable or one.ok
        return ToolInvokeResponse(
            name="lookup_metric",
            ok=usable,
            stop=not usable,
            result={
                "ok": usable,
                "stop": not usable,
                "company_code": args.company_code,  # type: ignore[attr-defined]
                "year": args.year,  # type: ignore[attr-defined]
                "scope": args.scope,  # type: ignore[attr-defined]
                "lookups": lookups,
                "message": "Mock：并列查数。" if usable else "Mock：全部科目无数据。",
            },
            error=None if usable else "全部科目无数据。",
            error_code=None if usable else "missing",
            request_id=ctx.request_id,
        )
    if name == "list_scope":
        return _list_scope(parsed, ctx)  # type: ignore[arg-type]
    if name == "verify_number":
        return _verify(parsed, ctx)  # type: ignore[arg-type]
    if name == "compare_peers":
        args = parsed  # type: ComparePeersArgs
        lookups = []
        for code in args.company_codes:  # type: ignore[attr-defined]
            one = _lookup(
                LookupMetricArgs(
                    company_code=code,
                    concept=args.concept,  # type: ignore[attr-defined]
                    year=args.year,  # type: ignore[attr-defined]
                    scope=args.scope,  # type: ignore[attr-defined]
                ),
                ctx,
            )
            lookups.append(one.result)
            if not one.ok:
                return ToolInvokeResponse(
                    name="compare_peers",
                    ok=False,
                    stop=True,
                    result={
                        "ok": False,
                        "stop": True,
                        "concept": args.concept,  # type: ignore[attr-defined]
                        "year": args.year,  # type: ignore[attr-defined]
                        "scope": args.scope,  # type: ignore[attr-defined]
                        "lookups": lookups,
                        "message": "Mock：至少一家无数据。",
                    },
                    error_code=one.error_code,
                    error=one.error,
                    request_id=ctx.request_id,
                )
        return ToolInvokeResponse(
            name="compare_peers",
            ok=True,
            stop=False,
            result={
                "ok": True,
                "stop": False,
                "concept": args.concept,  # type: ignore[attr-defined]
                "year": args.year,  # type: ignore[attr-defined]
                "scope": args.scope,  # type: ignore[attr-defined]
                "lookups": lookups,
                "message": "Mock：并列查数。",
            },
            request_id=ctx.request_id,
        )
    if name == "create_review_draft":
        return _fail(
            name,
            error_code="forbidden_write",
            message="Mock：写操作未开放。",
            request_id=ctx.request_id,
        )
    if name == "rag_search":
        return ToolInvokeResponse(
            name="rag_search",
            ok=True,
            stop=False,
            result={
                "ok": True,
                "stop": False,
                "outcome": "ok",
                "citations": [
                    {
                        "doc_id": "002594_2024",
                        "page": 88,
                        "snippet": "Mock 风险因素摘录",
                        "title": "比亚迪2024年年度报告",
                        "viewer_url": None,
                    }
                ],
                "message": "Mock：固定引用。",
            },
            request_id=ctx.request_id,
        )
    if name == "emit_conclusion":
        conclusion = parsed.model_dump() if isinstance(parsed, EmitConclusionArgs) else {}
        return ToolInvokeResponse(
            name="emit_conclusion",
            ok=True,
            stop=False,
            result={
                "ok": True,
                "stop": False,
                "conclusion": conclusion,
                "message": "Mock：结论已通过 Schema。",
            },
            request_id=ctx.request_id,
        )
    return _fail(
        name,
        error_code="unknown_tool",
        message=f"Mock 未实现 {name}。",
        request_id=ctx.request_id,
    )


def replay_or_run(
    name: str,
    parsed: BaseModel,
    ctx: ToolContext,
) -> ToolInvokeResponse:
    key = ctx.idempotency_key
    if key:
        cached = _IDEMPOTENCY.get((name, key))
        if cached is not None:
            replayed = cached.model_copy(update={"replayed": True})
            return replayed
    result = mock_invoke(name, parsed, ctx)
    if key:
        _IDEMPOTENCY[(name, key)] = result
    return result
