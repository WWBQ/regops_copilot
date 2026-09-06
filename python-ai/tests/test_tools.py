from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.asknum.lookup import MetricLookup
from app.db.fin_metric_repository import FinMetricRow
from app.rag.service import Citation, RagAnswer
from app.rag.trace import RagPrepareResult, RagTrace
from app.schemas.tools import (
    EmitConclusionArgs,
    ListScopeArgs,
    LookupMetricArgs,
    RagSearchArgs,
    VerifyNumberArgs,
)
from app.tools import invoke_tool, openai_tool_schemas, parse_claimed_yuan
from app.tools.rag import run_rag_search
from app.tools.scope import run_list_scope
from app.tools.verify import run_verify_number


def _row(
    *,
    concept: str = "revenue",
    status: str = "auto_accepted",
    value: Decimal = Decimal("777102455000"),
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
        raw_name="营业总收入",
        raw_value=str(value),
        page_no=None,
        bbox_json=None,
        parser="eastmoney_f10",
        status=status,
        review_reason=review_reason,
        xbrl_tag=None,
        content_hash="abc",
        created_at=datetime(2026, 9, 6),
        updated_at=datetime(2026, 9, 6),
    )


def _hit(*, outcome: str = "ok", row: FinMetricRow | None = None) -> MetricLookup:
    picked = row if row is not None else (_row() if outcome == "ok" else None)
    return MetricLookup(
        company_code="002594",
        concept="revenue",
        year=2024,
        scope="consolidated",
        outcome=outcome,
        row=picked,
        review_reason=picked.review_reason if picked else None,
    )


def test_catalog_has_five_readonly_tools():
    names = [item["function"]["name"] for item in openai_tool_schemas()]
    assert "lookup_metric" in names
    assert "compare_peers" in names
    assert "create_review_draft" in names
    assert "execute_sql" not in names


def test_lookup_metric_ok():
    with patch("app.tools.lookup.lookup_metric", return_value=_hit()):
        out = invoke_tool(
            "lookup_metric",
            {"company_code": "002594", "concept": "revenue", "year": 2024},
        )
    assert out.ok is True
    assert out.stop is False
    assert out.result["value_yuan"] == "777102455000"
    assert out.result["outcome"] == "ok"


def test_lookup_metric_human_review_stops_without_amount():
    row = _row(status="human_review", review_reason="critical_amount_mismatch")
    with patch("app.tools.lookup.lookup_metric", return_value=_hit(outcome="human_review", row=row)):
        out = invoke_tool(
            "lookup_metric",
            {"company_code": "000333", "concept": "revenue", "year": 2024},
        )
    assert out.ok is False
    assert out.stop is True
    assert out.result["value_yuan"] is None
    assert out.result["outcome"] == "human_review"


def test_lookup_metric_missing_stops():
    with patch("app.tools.lookup.lookup_metric", return_value=_hit(outcome="missing", row=None)):
        out = invoke_tool(
            "lookup_metric",
            {"company_code": "300750", "concept": "net_profit", "year": 2024},
        )
    assert out.ok is False
    assert out.stop is True
    assert out.result["outcome"] == "missing"


def test_lookup_rejects_unknown_concept():
    with pytest.raises(ValidationError):
        LookupMetricArgs(company_code="002594", concept="roe", year=2024)  # type: ignore[arg-type]


def test_verify_number_match_yi():
    with patch("app.tools.lookup.lookup_metric", return_value=_hit()):
        out = run_verify_number(
            VerifyNumberArgs(
                company_code="002594",
                concept="revenue",
                year=2024,
                claimed="7771.02455亿",
            )
        )
    assert out.ok is True
    assert out.verdict == "match"
    assert out.stop is False


def test_verify_number_mismatch_stops():
    with patch("app.tools.lookup.lookup_metric", return_value=_hit()):
        out = invoke_tool(
            "verify_number",
            {
                "company_code": "002594",
                "concept": "revenue",
                "year": 2024,
                "claimed": "1亿",
            },
        )
    assert out.ok is False
    assert out.stop is True
    assert out.result["verdict"] == "mismatch"


def test_verify_number_unavailable_when_review():
    row = _row(status="human_review")
    with patch("app.tools.lookup.lookup_metric", return_value=_hit(outcome="human_review", row=row)):
        out = run_verify_number(
            VerifyNumberArgs(
                company_code="000333",
                concept="revenue",
                year=2024,
                claimed="4091亿",
            )
        )
    assert out.verdict == "unavailable"
    assert out.stop is True
    assert out.fact_yuan is None


def test_parse_claimed_yuan():
    assert parse_claimed_yuan("1,000") == Decimal("1000")
    assert parse_claimed_yuan("2万") == Decimal("20000")
    assert parse_claimed_yuan("3亿元") == Decimal("300000000")


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_list_scope_groups_coverage():
    rows = [
        ("002594", 2024, "consolidated", "revenue"),
        ("002594", 2024, "consolidated", "net_profit"),
        ("601633", 2024, "consolidated", "net_profit"),
    ]
    with patch("app.tools.scope.get_connection", return_value=_Conn()), patch(
        "app.tools.scope.list_metric_coverage", return_value=rows
    ):
        out = run_list_scope(ListScopeArgs())
    assert out.companies == ["002594", "601633"]
    byd = next(item for item in out.items if item.company_code == "002594")
    assert byd.concepts == ["revenue", "net_profit"]
    assert out.stop is False


def test_list_scope_unknown_company_is_empty_not_invented():
    with patch("app.tools.scope.get_connection", return_value=_Conn()), patch(
        "app.tools.scope.list_metric_coverage", return_value=[]
    ):
        out = run_list_scope(ListScopeArgs(company_code="300750"))
    assert out.items == []
    assert "不要对该公司硬查" in out.message


def test_rag_search_ok_requires_page():
    answer = RagAnswer(
        messages=[],
        citations=[
            Citation(doc_id="002594_2024", page=88, snippet="风险因素", viewer_url="/v", title="比亚迪"),
            Citation(doc_id="002594_2024", page=0, snippet="无页", viewer_url=None, title=None),
        ],
        doc_ids=["002594_2024"],
    )
    prepared = RagPrepareResult(answer=answer, trace=RagTrace(question="q", outcome="ok"))
    with patch("app.tools.rag.prepare_chat_rag", return_value=prepared):
        out = run_rag_search(RagSearchArgs(question="比亚迪风险因素有哪些"), document_service=MagicMock())
    assert out.ok is True
    assert out.citations[0].page == 88
    assert len(out.citations) == 1


def test_rag_search_low_score_stops():
    prepared = RagPrepareResult(
        answer=None,
        trace=RagTrace(question="q", outcome="low_score"),
    )
    with patch("app.tools.rag.prepare_chat_rag", return_value=prepared):
        out = run_rag_search(RagSearchArgs(question="随便问问"), document_service=MagicMock())
    assert out.ok is False
    assert out.stop is True
    assert out.outcome == "low_score"
    assert out.citations == []


def test_emit_conclusion_rejects_overconfident_high_risk():
    out = invoke_tool(
        "emit_conclusion",
        {
            "conclusion": "存在重大合规风险",
            "risk_level": "高",
            "clause_refs": ["AML-1"],
            "confidence": 0.99,
        },
    )
    assert out.ok is False
    assert out.stop is True
    assert out.error


def test_emit_conclusion_valid():
    args = EmitConclusionArgs(
        conclusion="需关注关联交易披露",
        risk_level="中",
        clause_refs=["CSRC-12"],
        confidence=0.7,
    )
    out = invoke_tool("emit_conclusion", args.model_dump())
    assert out.ok is True
    assert "尚未提交" in out.result["message"]


def test_unknown_tool_stops():
    out = invoke_tool("execute_sql", {"sql": "select 1"})
    assert out.ok is False
    assert out.stop is True
    assert "未知工具" in (out.error or "")
