"""Ingest 三类检测：金额一致性、财务勾稽、证据坐标。

设计文档：docs/INGEST_VALIDATION.md
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

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

G2_CONCEPTS = frozenset(
    {
        "cash_begin",
        "net_cash_change",
        "profit_before_tax",
        "income_tax",
        "net_profit_attributable",
        "minority_interest",
    }
)

KNOWN_CONCEPTS = CRITICAL_CONCEPTS | G2_CONCEPTS

ALIASES: dict[str, str] = {
    "营业收入": "revenue",
    "营业总收入": "revenue",
    "TOTAL_OPERATE_INCOME": "revenue",
    "OPERATE_INCOME": "revenue",
    "净利润": "net_profit",
    "NETPROFIT": "net_profit",
    "NET_PROFIT": "net_profit",
    "资产总计": "total_assets",
    "资产合计": "total_assets",
    "TOTAL_ASSETS": "total_assets",
    "TOTALASSETS": "total_assets",
    "负债合计": "total_liabilities",
    "负债总计": "total_liabilities",
    "TOTAL_LIABILITIES": "total_liabilities",
    "TOTALLIAB": "total_liabilities",
    "TOTAL_LIAB": "total_liabilities",
    "所有者权益合计": "total_equity",
    "所有者权益（或股东权益）合计": "total_equity",
    "股东权益合计": "total_equity",
    "TOTAL_EQUITY": "total_equity",
    "TOTALEQUITY": "total_equity",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "NETCASH_OPERATE": "operating_cash_flow",
    "NETCASHOPERATE": "operating_cash_flow",
    "期末现金及现金等价物余额": "cash_end",
    "END_BAL_CASH": "cash_end",
    "END_CASH": "cash_end",
    "CASHEQUIVEND": "cash_end",
    "期初现金及现金等价物余额": "cash_begin",
    "BEGIN_BAL_CASH": "cash_begin",
    "BEGIN_CASH": "cash_begin",
    "CASHEQUIVBEGIN": "cash_begin",
    "现金及现金等价物净增加额": "net_cash_change",
    "CCE_ADD": "net_cash_change",
    "CASHNETEQUIV": "net_cash_change",
    "利润总额": "profit_before_tax",
    "TOTAL_PROFIT": "profit_before_tax",
    "所得税费用": "income_tax",
    "INCOME_TAX": "income_tax",
    "基本每股收益": "eps",
    "BASIC_EPS": "eps",
    "归属于母公司股东的净利润": "net_profit_attributable",
    "归属于母公司所有者的净利润": "net_profit_attributable",
    "PARENT_NETPROFIT": "net_profit_attributable",
    "PARENTNETPROFIT": "net_profit_attributable",
    "少数股东损益": "minority_interest",
    "少数股东净利润": "minority_interest",
    "MINORITY_INTEREST": "minority_interest",
    "MINORITYINTEREST": "minority_interest",
}

MISSING_TOKENS = frozenset({"", "-", "—", "--", "不适用", "N/A", "n/a", "None", "null"})

UNIT_SCALE: dict[str, Decimal] = {
    "元": Decimal("1"),
    "千元": Decimal("1000"),
    "万元": Decimal("10000"),
    "百万元": Decimal("1000000"),
    "亿元": Decimal("100000000"),
}

FactKey = tuple[str, str, str, str, str]


def resolve_concept(raw_name: str) -> str | None:
    """科目名 / 英文字段 → 标准 concept；未知返回 None。"""
    name = raw_name.strip()
    if name in ALIASES:
        return ALIASES[name]
    if name in KNOWN_CONCEPTS:
        return name
    upper = name.upper()
    if upper in ALIASES:
        return ALIASES[upper]
    return None


def fact_key(fact: dict[str, Any]) -> FactKey:
    return (
        str(fact["concept"]),
        str(fact["period"]),
        str(fact["scope"]),
        str(fact["currency"]),
        str(fact["statement"]),
    )


def yuan_from_any(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize_amount(raw_value: Any, unit: str) -> Decimal | None:
    """财报金额归一化到「元」。括号表示负数；横线/不适用 → None。"""
    if raw_value is None:
        return None
    if isinstance(raw_value, Decimal):
        text = format(raw_value, "f")
    elif isinstance(raw_value, (int, float)):
        text = format(Decimal(str(raw_value)), "f")
    else:
        text = str(raw_value).strip().replace(",", "").replace(" ", "")
    if text in MISSING_TOKENS:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    elif text.startswith("-"):
        negative = True
        text = text[1:]
    if text in MISSING_TOKENS:
        return None
    scale = UNIT_SCALE.get(unit)
    if scale is None:
        raise ValueError(f"unsupported unit: {unit}")
    try:
        value = Decimal(text) * scale
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {raw_value!r}") from exc
    return -value if negative else value


def amount_mismatch(standard_fact: dict[str, Any], other_fact: dict[str, Any]) -> tuple[bool, str]:
    """同一 fact_key 下比较归一化 value（字符串或 Decimal）。"""
    if fact_key(standard_fact) != fact_key(other_fact):
        return True, "金额上下文无法对齐"
    left = yuan_from_any(standard_fact.get("value"))
    right = yuan_from_any(other_fact.get("value"))
    if left is None or right is None:
        return True, f"金额不一致：{standard_fact.get('value')} != {other_fact.get('value')}"
    if left != right:
        return True, f"金额不一致：{format(left, 'f')} != {format(right, 'f')}"
    return False, ""


def detect_amount_conflicts(facts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一 fact_key 出现多个不同 value → G1 冲突（禁止静默择一）。"""
    grouped: dict[FactKey, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        grouped[fact_key(fact)].append(fact)
    conflicts: list[dict[str, Any]] = []
    for key, items in grouped.items():
        values: set[str | None] = set()
        for item in items:
            parsed = yuan_from_any(item.get("value"))
            values.add(None if parsed is None else format(parsed, "f"))
        if len(items) > 1 and len(values) > 1:
            conflicts.append(
                {
                    "fact_key": "|".join(key),
                    "reason": "critical_amount_mismatch",
                    "values": [item.get("value") for item in items],
                    "raw_names": [item.get("raw_name") for item in items],
                }
            )
    return conflicts


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


def validate_bbox(
    page_no: int | None,
    bbox: list[float] | tuple[float, ...] | None,
    *,
    page_width: float | None = None,
    page_height: float | None = None,
) -> tuple[bool, str]:
    """PDF 单元格 G3：必须有唯一页码 + 面积为正的 BBox。"""
    if page_no is None:
        return False, "missing_or_invalid_bbox: 缺少 page_no"
    if bbox is None or len(bbox) != 4:
        return False, "missing_or_invalid_bbox: 单元格缺少BBox"
    left, top, right, bottom = (float(x) for x in bbox)
    area = (right - left) * (bottom - top)
    if area <= 0 or left >= right or top >= bottom:
        return False, "missing_or_invalid_bbox: BBox超出页面或面积无效"
    if page_width is not None and page_height is not None:
        in_page = 0 <= left < right <= page_width and 0 <= top < bottom <= page_height
        if not in_page:
            return False, "missing_or_invalid_bbox: BBox超出页面或面积无效"
    return True, ""


def validate_fact_evidence(fact: dict[str, Any]) -> tuple[bool, str]:
    """G3：PDF 要 page+bbox；F10/web 用 content_hash 作为结构化溯源。"""
    source_type = fact.get("source_type") or "pdf"
    if source_type == "web":
        digest = str(fact.get("content_hash") or "")
        if not digest.startswith("sha256:"):
            return False, "missing_or_invalid_bbox: 结构化源缺少 content_hash"
        return True, ""
    return validate_bbox(
        fact.get("page_no"),
        fact.get("bbox"),
        page_width=fact.get("page_width"),
        page_height=fact.get("page_height"),
    )


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
    fact_key_value: str | None = None,
) -> dict[str, Any]:
    """关键金额冲突时禁止自动择一，进入人工复核。"""
    payload: dict[str, Any] = {"status": "human_review", "reason": reason}
    if standard_value is not None:
        payload["standard_value"] = standard_value
    if vlm_value is not None:
        payload["vlm_value"] = vlm_value
    if page_no is not None:
        payload["page_no"] = page_no
    if fact_key_value is not None:
        payload["fact_key"] = fact_key_value
    return payload
