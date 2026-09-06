"""评测样本筛选。"""

from app.eval.selection import normalize_categories, select_items


def test_normalize_categories_merges_and_dedupes():
    assert normalize_categories("banking, market", ["clause", "banking"]) == [
        "clause",
        "banking",
        "market",
    ]


def test_select_items_by_category_and_ids():
    items = [
        {"id": "a", "category": "clause"},
        {"id": "b", "category": "accounting"},
        {"id": "c", "category": "clause"},
    ]
    assert [row["id"] for row in select_items(items, categories=["clause"])] == ["a", "c"]
    assert [row["id"] for row in select_items(items, item_ids=["c", "a", "missing"])] == ["c", "a"]
    assert [row["id"] for row in select_items(items, categories=["clause"], limit=1)] == ["a"]
    # item_ids 优先于题型
    assert [row["id"] for row in select_items(items, categories=["accounting"], item_ids=["a"])] == ["a"]
