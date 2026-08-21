"""Ingest 三类检测：金额一致性、财务勾稽、证据坐标。

设计文档：docs/INGEST_VALIDATION.md
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

CRITICAL_CONCEPTS = frozenset(
    {
        "revenue",
        "net_profit",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "operating_cash_flow",
        "cash_end",
        "eps",
    }
)

ALIASES: dict[str, str] = {
    "营业收入": "revenue",
    "营业总收入": "revenue",
    "资产总计": "total_assets",
    "负债合计": "total_liabilities",
    "所有者权益合计": "total_equity",
}

UNIT_SCALE: dict[str, Decimal] = {
    "元": Decimal("1"),
    "千元": Decimal("1000"),
    "万元": Decimal("10000"),
    "百万元": Decimal("1000000"),
    "亿元": Decimal("100000000"),
}

FactKey = tuple[str, str, str, str, str]


def resolve_concept(raw_name: str) -> str | None:
    """中文科目名 → 标准 concept；未知返回 None。"""
    name = raw_name.strip()
    if name in ALIASES:
        return ALIASES[name]
    if name in CRITICAL_CONCEPTS:
        return name
    return None


def fact_key(fact: dict[str, Any]) -> FactKey:
    return (
        fact["concept"],
        fact["period"],
        fact["scope"],
        fact["currency"],
        fact["statement"],
    )


def normalize_amount(raw_value: str, unit: str) -> Decimal | None:
    """财报金额归一化到「元」。括号表示负数；横线/不适用 → None。"""
    text = raw_value.strip().replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if text in {"", "-", "—", "--", "不适用"}:
        return None
    scale = UNIT_SCALE.get(unit)
    if scale is None:
        raise ValueError(f"unsupported unit: {unit}")
    value = Decimal(text) * scale
    return -value if negative else value


def amount_mismatch(standard_fact: dict[str, Any], other_fact: dict[str, Any]) -> tuple[bool, str]:
    """同一 fact_key 下比较归一化 value（字符串或 Decimal）。"""
    if fact_key(standard_fact) != fact_key(other_fact):
        return True, "金额上下文无法对齐"
    left = standard_fact["value"]
    right = other_fact["value"]
    if str(left) != str(right):
        return True, f"金额不一致：{left} != {right}"
    return False, ""


def check_equation(
    name: str,
    left: Decimal | None,
    right_values: list[Decimal | None],
    display_unit: Decimal,
) -> tuple[bool, str]:
    """报表内勾稽；display_unit 为显示精度单位（如万元 = 10000）。"""
    if left is None or any(v is None for v in right_values):
        return False, f"{name}：必要字段缺失"
    difference = abs(left - sum(right_values))  # type: ignore[arg-type]
    tolerance = Decimal(len(right_values) + 1) * display_unit / Decimal("2")
    if difference > tolerance:
        return False, f"{name}勾稽失败：差额={difference}，允许误差={tolerance}"
    return True, ""


def validate_cell_source(document: Any, table: Any, cell: Any) -> tuple[bool, str | dict[str, Any]]:
    """Docling 单元格坐标校验。document/table/cell 为 Docling 对象。"""
    pages = {provenance.page_no for provenance in table.prov}
    if len(pages) != 1:
        return False, "单元格无法确定唯一页码"
    if cell.bbox is None:
        return False, "单元格缺少BBox"
    page_no = next(iter(pages))
    page = document.pages.get(page_no)
    if page is None or page.size is None:
        return False, "缺少页面尺寸"
    box = cell.bbox.to_top_left_origin(page_height=page.size.height)
    valid = (
        0 <= box.l < box.r <= page.size.width
        and 0 <= box.t < box.b <= page.size.height
        and box.area() > 0
    )
    if not valid:
        return False, "BBox超出页面或面积无效"
    return True, {"page_no": page_no, "bbox": box.model_dump(mode="json")}


def human_review_payload(
    reason: str,
    *,
    standard_value: str | None = None,
    vlm_value: str | None = None,
    page_no: int | None = None,
) -> dict[str, Any]:
    """关键金额冲突时禁止自动择一，进入人工复核。"""
    payload: dict[str, Any] = {"status": "human_review", "reason": reason}
    if standard_value is not None:
        payload["standard_value"] = standard_value
    if vlm_value is not None:
        payload["vlm_value"] = vlm_value
    if page_no is not None:
        payload["page_no"] = page_no
    return payload
