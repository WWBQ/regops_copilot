from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from app.asknum.aliases import clear_alias_cache
from app.asknum.citations import amount_needles, pick_unique_page
from app.asknum.lookup import lookup_metric, try_answer
from app.asknum.slots import looks_like_metric_question, parse_concepts, parse_slots
from app.asknum.trace import AsknumTrace
from app.db.fin_metric_repository import FinMetricRow


def _row(
    *,
    concept: str = "revenue",
    status: str = "auto_accepted",
    value: Decimal = Decimal("777102547000"),
    raw_name: str = "营业总收入",
    review_reason: str | None = None,
    company_code: str = "002594",
) -> FinMetricRow:
    return FinMetricRow(
        id=1,
        company_code=company_code,
        doc_id=f"{company_code}_2024",
        source_type="web",
        fact_key="k",
        concept=concept,
        period=date(2024, 12, 31),
        scope="consolidated",
        currency="CNY",
        statement="income",
        value_yuan=value,
        unit_raw="元",
        raw_name=raw_name,
        raw_value=str(value),
        page_no=None,
        bbox_json=None,
        parser="eastmoney_f10",
        status=status,
        review_reason=review_reason,
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


def test_parse_slots_metric_question():
    slots = parse_slots("比亚迪2024年营收多少")
    assert slots.company_codes == ("002594",)
    assert slots.concepts == ("revenue",)
    assert slots.year == 2024
    assert slots.years == (2024,)
    assert slots.year_defaulted is False
    assert slots.scope == "consolidated"
    assert slots.narrative is False


def test_parse_slots_narrative_skips_asknum():
    slots = parse_slots("比亚迪2024年营收为什么增长")
    assert slots.concepts == ("revenue",)
    assert slots.narrative is True
    assert try_answer("比亚迪2024年营收为什么增长", persist_trace=False) is None


def test_aliases_fall_back_without_db():
    clear_alias_cache()
    with patch("app.asknum.aliases.get_connection", side_effect=RuntimeError("offline")):
        assert parse_concepts("营收") == ["revenue"]
        assert parse_slots("比亚迪家底多少").company_codes == ("002594",)
    clear_alias_cache()


def test_aliases_read_from_table():
    clear_alias_cache()
    with patch("app.asknum.aliases.get_connection", return_value=_Conn()), patch(
        "app.asknum.aliases.list_asknum_aliases",
        return_value=[
            ("concept", "口袋进项", "revenue"),
            ("company", "车企甲", "002594"),
        ],
    ):
        assert parse_concepts("口袋进项") == ["revenue"]
        assert parse_slots("车企甲口袋进项多少").company_codes == ("002594",)
    clear_alias_cache()


def test_parse_concepts_longest_first():
    assert parse_concepts("归母净利润和总资产") == [
        "net_profit_attributable",
        "total_assets",
    ]


def test_parse_slots_colloquial_profit():
    slots = parse_slots("比亚迪赚了多少钱")
    assert slots.company_codes == ("002594",)
    assert slots.concepts == ("net_profit",)
    assert slots.narrative is False
    assert parse_slots("比亚迪进账多少").concepts == ("revenue",)
    assert parse_slots("格力股份家底多少").company_codes == ("000651",)
    assert parse_slots("格力股份家底多少").concepts == ("total_assets",)


def test_parse_slots_two_years():
    slots = parse_slots("比亚迪2023和2024的利润对比")
    assert slots.company_codes == ("002594",)
    assert slots.concepts == ()
    assert slots.years == (2023, 2024)
    assert slots.year_defaulted is False


def test_parse_slots_relative_year():
    last_year = parse_slots("比亚迪去年营收多少")
    assert last_year.year == 2023
    assert last_year.year_defaulted is False
    this_year = parse_slots("BYD今年净利润多少")
    assert this_year.company_codes == ("002594",)
    assert this_year.year == 2024
    assert this_year.year_defaulted is False


def test_parse_slots_qualitative_skips_asknum():
    slots = parse_slots("比亚迪利润怎么样")
    assert slots.narrative is True
    assert try_answer("比亚迪利润怎么样", persist_trace=False) is None

    operating = parse_slots("美的2024经营的怎么样")
    assert operating.company_codes == ("000333",)
    assert operating.years == (2024,)
    assert operating.narrative is True
    assert try_answer("美的2024经营的怎么样", persist_trace=False) is None


def test_parse_concepts_does_not_steal_profit_before_tax():
    assert parse_concepts("利润总额是多少") == ["profit_before_tax"]
    assert parse_concepts("营业利润多少") == []


def test_looks_like_metric_does_not_catch_chitchat():
    assert looks_like_metric_question("你好") is False
    assert looks_like_metric_question("比亚迪风险因素有哪些") is False
    assert looks_like_metric_question("查一下比亚迪财务数字") is True


def test_try_answer_clarify_amount_without_concept():
    result = try_answer("比亚迪今年数字多少", persist_trace=False)
    assert result is not None
    assert result.route == "metric_clarify"
    assert result.slots is not None
    assert result.slots.concepts == ()
    assert "指定指标" in result.reply


def test_try_answer_clarify_without_company():
    result = try_answer("营收多少", persist_trace=False)
    assert result is not None
    assert result.route == "metric_clarify"
    assert "指定公司" in result.reply
    assert result.slots is not None
    assert result.slots.concepts == ("revenue",)


def test_lookup_metric_ok():
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=[_row()]
    ):
        hit = lookup_metric(company_code="002594", concept="revenue", year=2024)
    assert hit.outcome == "ok"
    assert hit.row is not None
    assert hit.to_trace_dict()["value_yuan"] == "777102547000"


def test_lookup_metric_human_review():
    rows = [_row(status="human_review", review_reason="critical_amount_mismatch")]
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=rows
    ):
        hit = lookup_metric(company_code="000333", concept="revenue", year=2024)
    assert hit.outcome == "human_review"
    assert hit.to_trace_dict()["value_yuan"] is None


def test_lookup_metric_manually_accepted_after_review():
    rows = [_row(status="manually_accepted", value=Decimal("123.4500"), review_reason="人工复核通过")]
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=rows
    ):
        hit = lookup_metric(company_code="002594", concept="revenue", year=2024)
    assert hit.outcome == "ok"
    assert hit.row is rows[0]


def test_lookup_metric_rejected_remains_unavailable():
    rows = [_row(status="rejected", value=Decimal("123.4500"))]
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=rows
    ):
        hit = lookup_metric(company_code="002594", concept="revenue", year=2024)
    assert hit.outcome == "not_accepted"


def test_lookup_metric_missing():
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=[]
    ):
        hit = lookup_metric(company_code="300750", concept="net_profit", year=2024)
    assert hit.outcome == "missing"
    assert hit.row is None


def test_lookup_metric_accepted_conflict():
    rows = [
        _row(value=Decimal("100")),
        _row(value=Decimal("200")),
    ]
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=rows
    ):
        hit = lookup_metric(company_code="002594", concept="revenue", year=2024)
    assert hit.outcome == "accepted_conflict"
    assert hit.to_trace_dict()["value_yuan"] is None


def test_try_answer_returns_accepted_fact():
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=[_row()]
    ):
        result = try_answer("比亚迪2024年营业收入是多少", persist_trace=False)
    assert result is not None
    assert result.route == "metric"
    assert result.lookups[0].outcome == "ok"
    assert "777,102,547,000.00 元" in result.reply
    assert "约 7771.03 亿元" in result.reply
    assert "[1]" in result.reply
    assert "concept=" not in result.reply
    assert result.citations
    assert result.citations[0].kind == "facts"
    assert "company_code=002594" in (result.citations[0].href or "")


def test_english_raw_name_uses_chinese_label():
    from app.asknum.slots import concept_label

    assert concept_label("revenue", "TOTAL_OPERATE_INCOME") == "营业收入"
    assert concept_label("revenue", "营业总收入") == "营业总收入"


def test_try_answer_blocks_human_review():
    rows = [
        _row(
            status="human_review",
            review_reason="critical_amount_mismatch",
            raw_name="营业收入",
        )
    ]
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=rows
    ):
        result = try_answer("美的2024年营收多少", persist_trace=False)
    assert result is not None
    assert result.route == "metric_blocked"
    assert result.lookups[0].outcome == "human_review"
    assert "待人工复核" in result.reply
    assert "777,102,547,000" not in result.reply


def test_try_answer_missing_fact():
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=[]
    ), patch("app.asknum.lookup.list_company_metric_years", return_value=[]):
        result = try_answer("宁德时代2024年净利润多少", persist_trace=False)
    assert result is not None
    assert result.route == "metric_blocked"
    assert result.lookups[0].outcome == "missing"
    assert "没有" in result.reply
    assert "尚未写入" in result.reply


def test_try_answer_last_year_reports_coverage():
    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", return_value=[]
    ), patch("app.asknum.lookup.list_company_metric_years", return_value=[2024]):
        result = try_answer("比亚迪去年营收多少", persist_trace=False)
    assert result is not None
    assert result.route == "metric_blocked"
    assert result.slots is not None
    assert result.slots.year == 2023
    assert "没有 2023 年" in result.reply
    assert "777" not in result.reply


def test_try_answer_compares_two_companies_deterministically():
    values = {
        "002594": Decimal("777102547000"),
        "601633": Decimal("202195469900"),
    }

    def fake_find(_conn, *, company_code, concept, year, scope):
        return [
            _row(
                company_code=company_code,
                concept=concept,
                value=values[company_code],
            )
        ]

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ):
        result = try_answer(
            "比亚迪和长城汽车2024年营业收入谁更高",
            persist_trace=False,
        )

    assert result is not None
    assert result.route == "metric"
    assert result.intent == "asknum_compare"
    assert "确定性比较" in result.reply
    assert "比亚迪高于长城汽车" in result.reply
    assert "差额为 574,907,077,100.00 元" in result.reply
    assert len(result.lookups) == 2


def test_try_answer_refuses_comparison_when_one_company_is_missing():
    def fake_find(_conn, *, company_code, concept, year, scope):
        if company_code == "002594":
            return [_row(company_code=company_code, concept=concept)]
        return []

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ), patch("app.asknum.lookup.list_company_metric_years", return_value=[2024]):
        result = try_answer(
            "比亚迪和长城汽车2024年营业收入谁更高",
            persist_trace=False,
        )

    assert result is not None
    assert result.route == "metric_blocked"
    assert "拒绝直接比较" in result.reply
    assert "不会改用模型补全" in result.reply
    assert "确定性比较" not in result.reply


def test_try_answer_derived_looks_up_then_incomplete():
    def fake_find(_conn, *, company_code, concept, year, scope):
        if year == 2024 and concept in {"net_profit", "total_equity", "revenue"}:
            return [_row(concept=concept, company_code=company_code)]
        return []

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ), patch("app.asknum.lookup.list_company_metric_years", return_value=[2024]):
        roe = try_answer("比亚迪2024年ROE是多少", persist_trace=False)
        margin = try_answer("比亚迪2024年毛利率是多少", persist_trace=False)
        yoy = try_answer("比亚迪2024年营收同比多少", persist_trace=False)
    assert roe is not None and margin is not None and yoy is not None
    assert {roe.route, margin.route, yoy.route} == {"metric_blocked"}
    assert "数据不完整" in roe.reply and "加权平均净资产" in roe.reply
    assert [hit.concept for hit in roe.lookups] == ["net_profit", "total_equity"]
    assert "营业成本" in margin.reply and "未入库" in margin.reply
    assert any(hit.concept == "revenue" and hit.year == 2023 for hit in yoy.lookups)
    assert "2023" in yoy.reply
    assert "777" not in roe.reply
    assert "777" not in yoy.reply


def test_pick_unique_page_requires_amount():
    page, snippet = pick_unique_page(
        [
            (24, "营业总收入 777,102,455,000.00"),
            (80, "营业总收入 目录"),
        ],
        names=["营业总收入"],
        needles=amount_needles(Decimal("777102455000")),
    )
    assert page == 24
    assert snippet is not None
    page, snippet = pick_unique_page(
        [
            (24, "营业总收入 777,102,455,000.00"),
            (25, "营业总收入 777102455000"),
        ],
        names=["营业总收入"],
        needles=amount_needles(Decimal("777102455000")),
    )
    assert page is None


def test_try_answer_two_companies():
    def fake_find(_conn, *, company_code, concept, year, scope):
        value = Decimal("100") if company_code == "002594" else Decimal("200")
        return [_row(company_code=company_code, value=value, concept=concept)]

    with patch("app.asknum.lookup.get_connection", return_value=_Conn()), patch(
        "app.asknum.lookup.find_company_metrics", side_effect=fake_find
    ):
        result = try_answer("对比比亚迪和长城2024年营收", persist_trace=False)
    assert result is not None
    assert result.route == "metric"
    assert len(result.lookups) == 2
    assert "002594" in result.reply
    assert "601633" in result.reply


def test_try_answer_does_not_trace_chitchat():
    with patch("app.asknum.lookup.save_asknum_trace") as save:
        assert try_answer("你好", persist_trace=True) is None
    save.assert_not_called()


def test_try_answer_traces_narrative_skip():
    with patch("app.asknum.lookup.save_asknum_trace") as save:
        assert try_answer("比亚迪2024年营收为什么增长", persist_trace=True) is None
    save.assert_called_once()
    trace = save.call_args.args[0]
    assert isinstance(trace, AsknumTrace)
    assert trace.route == "skip"
    assert trace.concepts == ["revenue"]
    assert trace.narrative is True


def test_try_answer_traces_clarify():
    with patch("app.asknum.lookup.save_asknum_trace") as save:
        result = try_answer("营收多少", persist_trace=True, request_id="req-1")
    assert result is not None
    save.assert_called_once()
    trace = save.call_args.args[0]
    assert trace.route == "metric_clarify"
    assert trace.request_id == "req-1"
    assert trace.lookups == []
