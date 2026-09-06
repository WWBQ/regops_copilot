"""评测样本筛选：题型、题号、条数上限。"""

from __future__ import annotations

from typing import Any


def normalize_categories(
    category: str = "",
    categories: list[str] | None = None,
) -> list[str]:
    values: list[str] = []
    for raw in categories or []:
        text = str(raw).strip()
        if text:
            values.append(text)
    if category:
        for part in category.split(","):
            text = part.strip()
            if text:
                values.append(text)
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def normalize_item_ids(item_ids: list[str] | None) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw in item_ids or []:
        text = str(raw).strip()
        if text and text not in seen:
            seen.add(text)
            values.append(text)
    return values


def select_items(
    items: list[dict[str, Any]],
    *,
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    selected = list(items)
    ids = normalize_item_ids(item_ids)
    if ids:
        by_id = {str(item.get("id")): item for item in selected}
        selected = [by_id[item_id] for item_id in ids if item_id in by_id]
    elif categories:
        wanted = set(categories)
        selected = [item for item in selected if item.get("category") in wanted]
    if limit > 0:
        selected = selected[:limit]
    return selected
