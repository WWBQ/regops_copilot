"""verify_number：声称金额对回 fin_metric，对不上就停。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.schemas.tools import LookupMetricArgs, VerifyNumberArgs, VerifyNumberResult
from app.tools.lookup import run_lookup_metric

_RELATIVE_TOL = Decimal("0.0001")
_ABS_TOL = Decimal("0.01")


def parse_claimed_yuan(text: str) -> Decimal:
    raw = text.strip().replace(",", "").replace("，", "").replace(" ", "")
    multiplier = Decimal("1")
    if raw.endswith("亿元"):
        raw, multiplier = raw[:-2], Decimal("100000000")
    elif raw.endswith("亿"):
        raw, multiplier = raw[:-1], Decimal("100000000")
    elif raw.endswith("万元"):
        raw, multiplier = raw[:-2], Decimal("10000")
    elif raw.endswith("万"):
        raw, multiplier = raw[:-1], Decimal("10000")
    elif raw.endswith("元"):
        raw = raw[:-1]
    try:
        return Decimal(raw) * multiplier
    except InvalidOperation as exc:
        raise ValueError(f"无法解析金额：{text}") from exc


def _same_amount(claimed: Decimal, fact: Decimal) -> bool:
    tol = max(_ABS_TOL, abs(fact) * _RELATIVE_TOL)
    return abs(claimed - fact) <= tol


def run_verify_number(args: VerifyNumberArgs) -> VerifyNumberResult:
    claimed = parse_claimed_yuan(args.claimed)
    hit = run_lookup_metric(
        LookupMetricArgs(
            company_code=args.company_code,
            concept=args.concept,
            year=args.year,
            scope=args.scope,
        )
    )
    if not hit.ok or hit.value_yuan is None:
        return VerifyNumberResult(
            ok=False,
            stop=True,
            verdict="unavailable",
            lookup_outcome=hit.outcome,
            claimed_yuan=format(claimed, "f"),
            fact_yuan=None,
            message=f"无法核对：{hit.message}",
        )
    fact = Decimal(hit.value_yuan)
    matched = _same_amount(claimed, fact)
    if matched:
        return VerifyNumberResult(
            ok=True,
            stop=False,
            verdict="match",
            lookup_outcome="ok",
            claimed_yuan=format(claimed, "f"),
            fact_yuan=hit.value_yuan,
            message="声称金额与已通过事实一致。",
        )
    return VerifyNumberResult(
        ok=False,
        stop=True,
        verdict="mismatch",
        lookup_outcome="ok",
        claimed_yuan=format(claimed, "f"),
        fact_yuan=hit.value_yuan,
        message="声称金额与财务事实库不一致，停止，不得改口圆过去。",
    )


def verify_number_description() -> str:
    return (
        "把一段声称的财务数字对回 fin_metric（只认 auto_accepted）。"
        "claimed 可用元，或带亿/万。对不上、待复核或缺失时 stop=true。"
    )
