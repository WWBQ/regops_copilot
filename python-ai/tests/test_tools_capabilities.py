from app.tools import invoke_tool
from app.tools.capabilities import tool_capabilities, tool_schema
from app.tools.pii import mask_pii
from app.schemas.tools import ToolContext


def test_capabilities_lists_commands_and_forbids_sql():
    body = tool_capabilities()
    names = {item["name"] for item in body["commands"]}
    assert "lookup_metric" in names
    assert "compare_peers" in names
    assert "create_review_draft" in names
    assert "execute_sql" in body["forbidden"]
    lookup = next(item for item in body["commands"] if item["name"] == "lookup_metric")
    assert "properties" in lookup["input_schema"]


def test_schema_unknown_is_none():
    assert tool_schema("execute_sql") is None
    assert tool_schema("lookup_metric")["name"] == "lookup_metric"


def test_create_review_draft_refuses_write():
    out = invoke_tool(
        "create_review_draft",
        {"company_code": "002594", "title": "关联交易", "reason": "需复核"},
    )
    assert out.ok is False
    assert out.stop is True
    assert out.error_code == "forbidden_write"


def test_compare_peers_mock():
    out = invoke_tool(
        "compare_peers",
        {
            "company_codes": ["002594", "601633"],
            "concept": "net_profit",
            "year": 2024,
        },
        context=ToolContext(backend="mock"),
    )
    assert out.ok is True
    assert len(out.result["lookups"]) == 2


def test_mask_pii():
    text = mask_pii("联系 13812345678 身份证 110101199001011234 账号 6222021234567890123")
    assert "13812345678" not in text
    assert "110101199001011234" not in text
    assert "[手机号]" in text
    assert "[身份证]" in text
