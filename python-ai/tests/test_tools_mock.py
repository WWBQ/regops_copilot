from app.schemas.tools import ToolContext
from app.tools import clear_mock_state, invoke_tool


def setup_function() -> None:
    clear_mock_state()


def _mock(**kwargs) -> ToolContext:
    return ToolContext(backend="mock", **kwargs)


def test_mock_lookup_fixed_response():
    out = invoke_tool(
        "lookup_metric",
        {"company_code": "002594", "concept": "revenue", "year": 2024},
        context=_mock(),
    )
    assert out.ok is True
    assert out.result["value_yuan"] == "777102455000"
    assert out.error_code is None


def test_mock_missing_company():
    out = invoke_tool(
        "lookup_metric",
        {"company_code": "300750", "concept": "net_profit", "year": 2024},
        context=_mock(),
    )
    assert out.ok is False
    assert out.stop is True
    assert out.error_code == "missing"
    assert out.result["value_yuan"] is None


def test_mock_inject_missing():
    out = invoke_tool(
        "lookup_metric",
        {"company_code": "002594", "concept": "revenue", "year": 2024},
        context=_mock(inject="missing"),
    )
    assert out.error_code == "missing"
    assert out.stop is True


def test_mock_unauthorized_cross_dept():
    out = invoke_tool(
        "lookup_metric",
        {"company_code": "000333", "concept": "revenue", "year": 2024},
        context=_mock(dept="research"),
    )
    assert out.ok is False
    assert out.error_code == "unauthorized"
    assert "不能查询" in (out.error or "")


def test_mock_compliance_can_list_midea_scope_but_lookup_still_missing():
    scoped = invoke_tool(
        "list_scope",
        {"company_code": "002594"},
        context=_mock(dept="compliance"),
    )
    assert scoped.ok is True
    assert "002594" in scoped.result["companies"]


def test_mock_timeout_does_not_sleep():
    out = invoke_tool(
        "lookup_metric",
        {"company_code": "002594", "concept": "revenue", "year": 2024},
        context=_mock(inject="timeout"),
    )
    assert out.error_code == "timeout"
    assert out.stop is True
    assert out.result == {}


def test_mock_duplicate_replays_same_payload():
    first = invoke_tool(
        "lookup_metric",
        {"company_code": "002594", "concept": "revenue", "year": 2024},
        context=_mock(idempotency_key="req-1"),
    )
    second = invoke_tool(
        "lookup_metric",
        {"company_code": "002594", "concept": "net_profit", "year": 2024},
        context=_mock(idempotency_key="req-1"),
    )
    assert first.replayed is False
    assert second.replayed is True
    assert second.result["concept"] == "revenue"
    assert second.result["value_yuan"] == first.result["value_yuan"]


def test_mock_compare_peers_unauthorized():
    out = invoke_tool(
        "compare_peers",
        {
            "company_codes": ["002594", "000333"],
            "concept": "net_profit",
            "year": 2024,
        },
        context=_mock(dept="research"),
    )
    assert out.ok is False
    assert out.error_code == "unauthorized"


def test_mock_verify_match_and_mismatch():
    hit = invoke_tool(
        "verify_number",
        {
            "company_code": "002594",
            "concept": "revenue",
            "year": 2024,
            "claimed": "777102455000",
        },
        context=_mock(),
    )
    miss = invoke_tool(
        "verify_number",
        {
            "company_code": "002594",
            "concept": "revenue",
            "year": 2024,
            "claimed": "1亿",
        },
        context=_mock(),
    )
    assert hit.result["verdict"] == "match"
    assert miss.result["verdict"] == "mismatch"
    assert miss.stop is True
