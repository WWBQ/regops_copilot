"""G2 财务勾稽：ACCOUNTING_RULES R01–R03。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.ingest.validation import check_equation, yuan_from_any

DISPLAY_UNIT_YUAN = Decimal("1")


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    name: str
    passed: bool
    message: str
    concepts: tuple[str, ...]
    left: str | None = None
    right: str | None = None

    def to_dict(self) -> dict[str, str | bool | None | list[str]]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "concepts": list(self.concepts),
            "left": self.left,
            "right": self.right,
        }


def _get(values: Mapping[str, Decimal | None], name: str) -> Decimal | None:
    return values.get(name)


def _fmt(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def check_r01(
    values: Mapping[str, Decimal | None],
    *,
    display_unit: Decimal = DISPLAY_UNIT_YUAN,
) -> RuleResult:
    """资产总计 = 负债合计 + 所有者权益合计。"""
    assets = _get(values, "total_assets")
    liab = _get(values, "total_liabilities")
    equity = _get(values, "total_equity")
    passed, err = check_equation(
        "R01 资产负债表",
        assets,
        [liab, equity],
        display_unit,
    )
    if passed:
        message = ""
    elif err.endswith("必要字段缺失"):
        message = err
    else:
        right = None if liab is None or equity is None else liab + equity
        diff = None if assets is None or right is None else abs(assets - right)
        message = (
            f"资产负债表勾稽失败：资产总计 {_fmt(assets)} ≠ "
            f"负债合计 {_fmt(liab)} + 权益合计 {_fmt(equity)}，"
            f"差额 {format(diff, 'f') if diff is not None else 'n/a'}"
            f"（允许误差 {format((Decimal(len([liab, equity]) + 1) * display_unit / Decimal('2')), 'f')}）"
        )
    return RuleResult(
        rule_id="R01",
        name="资产负债表恒等式",
        passed=passed,
        message=message,
        concepts=("total_assets", "total_liabilities", "total_equity"),
        left=_fmt(assets),
        right=_fmt(None if liab is None or equity is None else liab + equity),
    )


def check_r02(
    values: Mapping[str, Decimal | None],
    *,
    display_unit: Decimal = DISPLAY_UNIT_YUAN,
) -> RuleResult:
    """期末现金 = 期初现金 + 现金净增加额。"""
    cash_end = _get(values, "cash_end")
    cash_begin = _get(values, "cash_begin")
    net_change = _get(values, "net_cash_change")
    passed, err = check_equation(
        "R02 现金流量表",
        cash_end,
        [cash_begin, net_change],
        display_unit,
    )
    if passed:
        message = ""
    elif err.endswith("必要字段缺失"):
        message = err
    else:
        right = None if cash_begin is None or net_change is None else cash_begin + net_change
        diff = None if cash_end is None or right is None else abs(cash_end - right)
        message = (
            f"现金流量表勾稽失败：期末现金 {_fmt(cash_end)} ≠ "
            f"期初 {_fmt(cash_begin)} + 净增加额 {_fmt(net_change)}，"
            f"差额 {format(diff, 'f') if diff is not None else 'n/a'}"
        )
    return RuleResult(
        rule_id="R02",
        name="现金期末余额",
        passed=passed,
        message=message,
        concepts=("cash_end", "cash_begin", "net_cash_change"),
        left=_fmt(cash_end),
        right=_fmt(
            None if cash_begin is None or net_change is None else cash_begin + net_change
        ),
    )


def check_r03(
    values: Mapping[str, Decimal | None],
    *,
    display_unit: Decimal = DISPLAY_UNIT_YUAN,
) -> RuleResult:
    """净利润 = 利润总额 - 所得税费用。"""
    net_profit = _get(values, "net_profit")
    pbt = _get(values, "profit_before_tax")
    tax = _get(values, "income_tax")
    tax_as_right = None if tax is None else -tax
    passed, err = check_equation(
        "R03 利润表",
        net_profit,
        [pbt, tax_as_right],
        display_unit,
    )
    if passed:
        message = ""
    elif err.endswith("必要字段缺失"):
        message = err
    else:
        right = None if pbt is None or tax is None else pbt - tax
        diff = None if net_profit is None or right is None else abs(net_profit - right)
        message = (
            f"利润表勾稽失败：净利润 {_fmt(net_profit)} ≠ "
            f"利润总额 {_fmt(pbt)} - 所得税 {_fmt(tax)}，"
            f"差额 {format(diff, 'f') if diff is not None else 'n/a'}"
        )
    return RuleResult(
        rule_id="R03",
        name="净利润",
        passed=passed,
        message=message,
        concepts=("net_profit", "profit_before_tax", "income_tax"),
        left=_fmt(net_profit),
        right=_fmt(None if pbt is None or tax is None else pbt - tax),
    )


RULE_CHECKERS = (check_r01, check_r02, check_r03)


def run_reconciliation(
    values: Mapping[str, Decimal | None | str | int | float],
    *,
    display_unit: Decimal = DISPLAY_UNIT_YUAN,
) -> list[RuleResult]:
    normalized: dict[str, Decimal | None] = {
        key: yuan_from_any(value) for key, value in values.items()
    }
    return [checker(normalized, display_unit=display_unit) for checker in RULE_CHECKERS]
