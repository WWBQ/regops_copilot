"""lookup_metric 工具：只返回 auto_accepted；可一次传 1–5 个科目。"""

from __future__ import annotations

from app.asknum.lookup import lookup_metric
from app.asknum.slots import CONCEPT_LABELS, SCOPE_LABELS, concept_label
from app.schemas.tools import LookupMetricArgs, LookupMetricResult, LookupMetricsResult

_OUTCOME_MSG = {
    "ok": "已命中已通过记录。",
    "human_review": "该科目待人工复核，不能当作业数字。",
    "missing": "财务事实库没有这条记录。",
    "accepted_conflict": "已通过记录存在多个不同取值，停止以免选错口径。",
    "not_accepted": "已入库但未通过质量门，不返回数字。",
}


def _lookup_one(*, company_code: str, concept: str, year: int, scope: str) -> LookupMetricResult:
    hit = lookup_metric(
        company_code=company_code,
        concept=concept,
        year=year,
        scope=scope,
    )
    label = concept_label(hit.concept, hit.row.raw_name if hit.row else None)
    scope_label = SCOPE_LABELS.get(hit.scope, hit.scope)
    ok = hit.outcome == "ok"
    value = None
    if ok and hit.row is not None and hit.row.value_yuan is not None:
        value = format(hit.row.value_yuan, "f")
    return LookupMetricResult(
        ok=ok,
        stop=not ok,
        outcome=hit.outcome,  # type: ignore[arg-type]
        company_code=hit.company_code,
        concept=hit.concept,
        year=hit.year,
        scope=hit.scope,
        value_yuan=value,
        raw_name=hit.row.raw_name if hit.row else None,
        fact_key=hit.row.fact_key if hit.row else None,
        doc_id=hit.row.doc_id if hit.row else None,
        status=hit.row.status if hit.row else None,
        review_reason=hit.review_reason or (hit.row.review_reason if hit.row else None),
        message=(
            f"{company_code} {hit.year} 年{scope_label}「{label}」{_OUTCOME_MSG[hit.outcome]}"
            if hit.outcome in _OUTCOME_MSG
            else _OUTCOME_MSG["missing"]
        ),
    )


def run_lookup_metric(args: LookupMetricArgs) -> LookupMetricResult | LookupMetricsResult:
    names = list(args.concepts or [args.concept])
    lookups = [
        _lookup_one(
            company_code=args.company_code,
            concept=str(concept),
            year=args.year,
            scope=args.scope,
        )
        for concept in names
        if concept
    ]
    if len(lookups) == 1:
        return lookups[0]
    usable = any(item.ok for item in lookups)
    blocked = sum(1 for item in lookups if not item.ok)
    return LookupMetricsResult(
        ok=usable,
        stop=not usable,
        company_code=args.company_code,
        year=args.year,
        scope=args.scope,
        lookups=lookups,
        message=(
            f"已并列 {len(lookups)} 科，未手算差额或比率。"
            + (f"其中 {blocked} 科待复核或缺失，不能当作业数字。" if blocked else "")
        ),
    )


def lookup_metric_description() -> str:
    labels = "、".join(f"{key}={label}" for key, label in CONCEPT_LABELS.items())
    return (
        "按证券代码、年份、报表口径查询财务事实库。concepts 传科目列表，单科只放一个元素，一次最多 5 个。"
        "也可只传 concept。"
        "只返回 status=auto_accepted 的数字；待复核、缺失或多值冲突时该科 ok=false 且无金额，不得编造。"
        "多科时其它科仍返回。经营概况一次调用即可（优先 revenue、net_profit_attributable、operating_cash_flow）。"
        f"concept 仅限：{labels}。"
    )
