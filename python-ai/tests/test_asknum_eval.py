"""W4 问数黄金集：结构校验 + 泄露检测 + 有库时全量回归。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.eval.asknum_runner import (
    _reply_leaked_amount,
    load_golden,
    run_asknum_eval,
    run_item,
)
from app.eval.registry import GOLDEN_DIR, validate_golden_payload

GOLDEN_PATH = GOLDEN_DIR / "w4_asknum_20.json"


def _fin_metric_ready() -> bool:
    try:
        from app.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.fin_metric')")
                if cur.fetchone()[0] is None:
                    return False
                cur.execute("SELECT COUNT(*) FROM fin_metric")
                return int(cur.fetchone()[0]) >= 20
    except Exception:
        return False


requires_fin_metric = pytest.mark.skipif(
    not _fin_metric_ready(),
    reason="fin_metric table empty or missing",
)


def test_golden_set_shape():
    payload = load_golden(GOLDEN_PATH)
    items = payload["items"]
    ids = [item["id"] for item in items]
    assert len(items) == 20
    assert len(set(ids)) == 20
    assert validate_golden_payload(payload, runner="w4_asknum") == 20
    routes = {item["expected_route"] for item in items}
    assert routes == {"metric", "metric_blocked", "metric_clarify", "skip"}
    for item in items:
        assert item.get("question")
        if item["expected_route"] != "metric":
            assert item.get("expect_no_amount") is True


def test_leak_detector_ignores_stock_code():
    assert not _reply_leaked_amount("请指定公司（如比亚迪 / 002594）后再查询。")
    assert not _reply_leaked_amount("待人工复核（critical_amount_mismatch），不返回该数字。")
    assert _reply_leaked_amount("营业收入为 777,102,455,000.00 元（约 7771.02 亿元）。")
    assert _reply_leaked_amount("基本每股收益为 4.61 元/股。")


def test_run_item_skip_without_db():
    row = run_item(
        {
            "id": "t-skip",
            "category": "skip",
            "question": "比亚迪2024年营收为什么增长",
            "expected_route": "skip",
            "expected_companies": ["002594"],
            "expected_concepts": ["revenue"],
            "expect_no_amount": True,
        }
    )
    assert row["passed"] is True
    assert row["actual_route"] == "skip"
    assert row["leaked"] is False


def test_run_item_detects_route_mismatch():
    row = run_item(
        {
            "id": "t-bad",
            "question": "营收多少",
            "expected_route": "metric",
            "expect_no_amount": False,
        }
    )
    assert row["passed"] is False
    assert row["actual_route"] == "metric_clarify"


def test_cannot_overwrite_builtin_asknum_golden():
    from app.eval.registry import save_golden_set

    with pytest.raises(ValueError, match="内置黄金集不可覆盖"):
        save_golden_set(
            filename="w4_asknum_20.json",
            content={"items": [{"id": "x", "question": "营收多少", "expected_route": "skip"}]},
            runner="w4_asknum",
        )


@requires_fin_metric
def test_live_golden_has_no_regression():
    with patch("app.asknum.lookup.save_asknum_trace") as save:
        report = run_asknum_eval(golden_path=GOLDEN_PATH)
    save.assert_not_called()
    summary = report["summary"]
    assert summary["total"] == 20
    assert summary["leak_count"] == 0
    assert summary["accuracy"] == 1.0, [row for row in report["results"] if not row["passed"]]
