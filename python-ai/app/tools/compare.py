"""compare_peers：同业只读对比，逐条 lookup，不手算差额或比率。"""

from __future__ import annotations

from app.schemas.tools import ComparePeersArgs, ComparePeersResult, LookupMetricArgs, LookupMetricResult
from app.tools.lookup import run_lookup_metric


def run_compare_peers(args: ComparePeersArgs) -> ComparePeersResult:
    lookups: list[LookupMetricResult] = []
    for code in args.company_codes:
        hit = run_lookup_metric(
            LookupMetricArgs(
                company_code=code,
                concept=args.concept,
                year=args.year,
                scope=args.scope,
            )
        )
        if not isinstance(hit, LookupMetricResult):
            raise TypeError("compare_peers 只并列单科结果")
        lookups.append(hit)
    ok = all(item.ok for item in lookups)
    return ComparePeersResult(
        ok=ok,
        stop=not ok,
        concept=args.concept,
        year=args.year,
        scope=args.scope,
        lookups=lookups,
        message="已逐条查数，未计算差额或比率。" if ok else "至少一家无法给出已通过数字，停止。",
    )


def compare_peers_description() -> str:
    return (
        "对比 2–5 家公司同一指标、同一年、同一口径。"
        "只并列 lookup_metric 结果，不手算同比、差额或比率。"
        "任一家缺失或待复核则 stop。"
    )
