"""list_scope：库里有哪家、哪年、哪些已通过指标。"""

from __future__ import annotations

from collections import defaultdict

from app.db.connection import get_connection
from app.db.fin_metric_repository import list_metric_coverage
from app.documents.titles import COMPANY_DISPLAY_NAMES
from app.schemas.tools import ListScopeArgs, ListScopeResult, ScopeItem


def run_list_scope(args: ListScopeArgs) -> ListScopeResult:
    with get_connection() as conn:
        rows = list_metric_coverage(
            conn,
            company_code=args.company_code,
            year=args.year,
            scope=args.scope,
            accepted_only=args.accepted_only,
        )
    grouped: dict[tuple[str, int, str], list[str]] = defaultdict(list)
    for company_code, year, scope, concept in rows:
        key = (company_code, year, scope)
        if concept not in grouped[key]:
            grouped[key].append(concept)
    items = [
        ScopeItem(
            company_code=company_code,
            company_name=COMPANY_DISPLAY_NAMES.get(company_code, company_code),
            year=year,
            scope=scope,
            concepts=concepts,
        )
        for (company_code, year, scope), concepts in grouped.items()
    ]
    companies = sorted({item.company_code for item in items})
    years = sorted({item.year for item in items}, reverse=True)
    if args.company_code and not items:
        message = f"{args.company_code} 在当前过滤条件下没有已通过事实，不要对该公司硬查数字。"
        return ListScopeResult(
            ok=True,
            stop=False,
            companies=[],
            years=[],
            items=[],
            message=message,
        )
    message = (
        f"已通过覆盖 {len(companies)} 家、{len(years)} 个年份、{len(items)} 组口径。"
        if items
        else "财务事实库当前没有已通过记录。"
    )
    return ListScopeResult(
        ok=True,
        stop=False,
        companies=companies,
        years=years,
        items=items,
        message=message,
    )


def list_scope_description() -> str:
    return (
        "列出财务事实库里已入库（默认仅 auto_accepted）的公司、年份、口径和指标。"
        "问未入库公司或年份之前先调这个工具，避免对空库硬查。"
    )
