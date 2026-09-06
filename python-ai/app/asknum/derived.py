"""派生问数：先查组成科目，缺了再说数据不完整，不直接拒。"""

from __future__ import annotations

from dataclasses import dataclass

from app.asknum.slots import (
    CONCEPT_LABELS,
    DEFAULT_REPORT_YEAR,
    AsknumSlots,
    has_unsupported_period,
    is_unsupported_ratio,
    parse_concepts,
)

_QUARTER_RE_LABELS: tuple[tuple[str, str], ...] = (
    ("一季度", "一季度"),
    ("二季度", "二季度"),
    ("三季度", "三季度"),
    ("四季度", "四季度"),
    ("q1", "一季度"),
    ("q2", "二季度"),
    ("q3", "三季度"),
    ("q4", "四季度"),
    ("第一季", "一季度"),
    ("第二季", "二季度"),
    ("第三季", "三季度"),
    ("第四季", "四季度"),
    ("半年报", "半年度"),
    ("中报", "半年度"),
)


@dataclass(frozen=True)
class DerivedPart:
    """要核对的一块。concept 为空表示库里没有这类直读科目/期间。"""

    label: str
    year: int
    scope: str
    concept: str | None = None


@dataclass(frozen=True)
class DerivedNeed:
    kind: str
    target_label: str
    parts: tuple[DerivedPart, ...]


def _base_concept(question: str, slots: AsknumSlots) -> str | None:
    if slots.concepts:
        return slots.concepts[0]
    found = parse_concepts(question)
    return found[0] if found else None


def _quarter_label(question: str) -> str | None:
    lowered = question.casefold()
    for alias, label in _QUARTER_RE_LABELS:
        if alias in lowered or alias in question:
            return label
    return None


def parse_derived_need(question: str, slots: AsknumSlots) -> DerivedNeed | None:
    """识别 ROE / 毛利率 / 同比 / 季度等；认不出则 None。"""
    scope = slots.scope
    year = slots.year
    if is_unsupported_ratio(question):
        lowered = question.casefold()
        if "毛利率" in question or "销售毛利率" in question:
            return DerivedNeed(
                kind="gross_margin",
                target_label="毛利率",
                parts=(
                    DerivedPart("营业收入", year, scope, "revenue"),
                    DerivedPart("营业成本", year, scope, None),
                ),
            )
        if "净利率" in question or "销售净利率" in question:
            return DerivedNeed(
                kind="net_margin",
                target_label="净利率",
                parts=(
                    DerivedPart("营业收入", year, scope, "revenue"),
                    DerivedPart("净利润", year, scope, "net_profit"),
                    DerivedPart("净利率披露行", year, scope, None),
                ),
            )
        if "研发" in question:
            return DerivedNeed(
                kind="rd",
                target_label="研发投入",
                parts=(DerivedPart("研发投入", year, scope, None),),
            )
        if "roe" in lowered or "净资产收益率" in question:
            return DerivedNeed(
                kind="roe",
                target_label="净资产收益率（ROE）",
                parts=(
                    DerivedPart("净利润", year, scope, "net_profit"),
                    DerivedPart("所有者权益合计", year, scope, "total_equity"),
                    DerivedPart("加权平均净资产", year, scope, None),
                ),
            )
        return DerivedNeed(
            kind="ratio",
            target_label="该比率",
            parts=(DerivedPart("对应披露行", year, scope, None),),
        )

    if not has_unsupported_period(question):
        return None

    concept = _base_concept(question, slots)
    quarter = _quarter_label(question)
    label = CONCEPT_LABELS.get(concept, "该指标") if concept else "该指标"

    if quarter:
        parts = []
        if concept:
            parts.append(DerivedPart(f"{year} 年报期末{label}", year, scope, concept))
        parts.append(DerivedPart(f"{year} 年{quarter}期间", year, scope, None))
        return DerivedNeed(kind="quarter", target_label=f"{quarter}{label}", parts=tuple(parts))

    if "近三年" in question or "连续三年" in question:
        if not concept:
            return None
        return DerivedNeed(
            kind="multi_year",
            target_label=f"近三年{label}",
            parts=tuple(
                DerivedPart(f"{y} 年{label}", y, scope, concept)
                for y in (year, year - 1, year - 2)
            ),
        )
    if "近两年" in question:
        if not concept:
            return None
        return DerivedNeed(
            kind="multi_year",
            target_label=f"近两年{label}",
            parts=tuple(
                DerivedPart(f"{y} 年{label}", y, scope, concept) for y in (year, year - 1)
            ),
        )
    if "同比" in question or "环比" in question or "增长率" in question:
        if not concept:
            return None
        prior = year - 1 if year else DEFAULT_REPORT_YEAR - 1
        kind_label = "同比" if "环比" not in question else "环比"
        return DerivedNeed(
            kind="yoy",
            target_label=f"{label}{kind_label}",
            parts=(
                DerivedPart(f"{year} 年{label}", year, scope, concept),
                DerivedPart(f"{prior} 年{label}", prior, scope, concept),
            ),
        )
    return None
