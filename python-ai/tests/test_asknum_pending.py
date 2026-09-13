from decimal import Decimal
from unittest.mock import patch

from app.asknum.lookup import try_answer
from app.asknum.pending import pending_hint, reset_pending_store
from app.asknum.slots import parse_slots
from app.db.fin_metric_repository import FinMetricRow
from datetime import date, datetime


def setup_function() -> None:
    reset_pending_store()


def teardown_function() -> None:
    reset_pending_store()


def _row(*, year: int = 2024, value: Decimal = Decimal("100"), concept: str = "net_profit") -> FinMetricRow:
    return FinMetricRow(
        id=1,
        company_code="002594",
        doc_id=f"002594_{year}",
        source_type="web",
        fact_key="k",
        concept=concept,
        period=date(year, 12, 31),
        scope="consolidated",
        currency="CNY",
        statement="income",
        value_yuan=value,
        unit_raw="元",
        raw_name="净利润",
        raw_value=str(value),
        page_no=None,
        bbox_json=None,
        parser="eastmoney_f10",
        status="auto_accepted",
        review_reason=None,
        xbrl_tag=None,
        content_hash="abc",
        created_at=datetime(2026, 9, 5),
        updated_at=datetime(2026, 9, 5),
    )


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


SESSION = "pending-slot-session"


def test_pending_hint_missing_metric():
    slots = parse_slots("比亚迪2023和2024的利润对比")
    assert pending_hint(slots) == "正在补充查询：比亚迪｜2023–2024｜缺少指标"


def test_three_turns_company_then_metric_then_lookup():
    first = try_answer("比亚迪2023和2024的利润对比", persist_trace=False, session_id=SESSION)
    assert first is not None
    assert first.route == "metric_clarify"
    assert first.pending_request is not None
    assert first.pending_request["company"] == "002594"
    assert first.pending_request["years"] == [2023, 2024]
    assert first.pending_request["metric"] is None
    assert first.pending_request["missing"] == ["metric"]
    assert first.pending_request["intent"] == "asknum_compare"
    assert "缺少指标" in first.pending_request["hint"]

    def fake_find(_conn, *, company_code, concept, year, scope):
        return [_row(year=year, value=Decimal("200") if year == 2024 else Decimal("100"))]

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ), patch("app.asknum.lookup.build_lookup_cites", return_value=()):
        second = try_answer("净利润", persist_trace=False, session_id=SESSION)
    assert second is not None
    assert second.route == "metric"
    assert second.pending_request is None
    assert second.slots is not None
    assert second.slots.company_codes == ("002594",)
    assert second.slots.concepts == ("net_profit",)
    assert second.slots.years == (2023, 2024)
    assert [hit.year for hit in second.lookups] == [2023, 2024]
    assert "2023" in second.reply and "2024" in second.reply
    assert "100.00 元" in second.reply
    assert "200.00 元" in second.reply


def test_metric_first_then_company_fills_pending():
    first = try_answer("2023和2024年的净利润对比", persist_trace=False, session_id=SESSION)
    assert first is not None
    assert first.route == "metric_clarify"
    assert first.pending_request is not None
    assert first.pending_request["missing"] == ["company"]
    assert first.pending_request["metric"] == "net_profit"

    def fake_find(_conn, *, company_code, concept, year, scope):
        return [_row(year=year, value=Decimal(str(year)))]

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ), patch("app.asknum.lookup.build_lookup_cites", return_value=()):
        second = try_answer("比亚迪", persist_trace=False, session_id=SESSION)
    assert second is not None
    assert second.route == "metric"
    assert second.pending_request is None
    assert second.slots is not None
    assert second.slots.company_codes == ("002594",)
    assert second.slots.years == (2023, 2024)
    assert second.slots.concepts == ("net_profit",)
    assert second.intent == "asknum_compare"


def test_topic_change_clears_pending():
    first = try_answer("比亚迪2023和2024的利润对比", persist_trace=False, session_id=SESSION)
    assert first is not None and first.pending_request is not None
    assert try_answer("换个话题", persist_trace=False, session_id=SESSION) is None
    third = try_answer("净利润", persist_trace=False, session_id=SESSION)
    assert third is not None
    assert third.route == "metric_clarify"
    assert third.pending_request is not None
    assert third.pending_request["missing"] == ["company"]


def test_hello_keeps_pending():
    first = try_answer("比亚迪2023和2024的利润对比", persist_trace=False, session_id=SESSION)
    assert first is not None and first.pending_request is not None
    assert try_answer("你好", persist_trace=False, session_id=SESSION) is None

    def fake_find(_conn, *, company_code, concept, year, scope):
        return [_row(year=year)]

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ), patch("app.asknum.lookup.build_lookup_cites", return_value=()):
        again = try_answer("净利润", persist_trace=False, session_id=SESSION)
    assert again is not None
    assert again.slots is not None
    assert again.slots.company_codes == ("002594",)
    assert again.route == "metric"
