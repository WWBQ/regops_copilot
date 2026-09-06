import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.mcp.client import McpClientError, McpHttpClient
from app.mcp.protocol import INVALID_PARAMS, METHOD_NOT_FOUND, PARSE_ERROR
from app.mcp.server import handle_mcp, parse_and_handle
from app.tools import clear_mock_state


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_mock():
    clear_mock_state()
    yield
    clear_mock_state()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_initialize_and_list_tools():
    init = handle_mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init is not None
    assert init.error is None
    assert init.result["serverInfo"]["name"] == "regops-tools"
    listed = handle_mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [item["name"] for item in listed.result["tools"]]
    assert "lookup_metric" in names
    assert "inputSchema" in listed.result["tools"][0]


def test_method_not_found_and_parse_error():
    missing = handle_mcp({"jsonrpc": "2.0", "id": 3, "method": "agents/run"})
    assert missing.error.code == METHOD_NOT_FOUND
    parsed = parse_and_handle("{not-json")
    assert parsed.error.code == PARSE_ERROR


def test_tools_call_requires_name():
    out = handle_mcp({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {}})
    assert out.error.code == INVALID_PARAMS


def test_tools_call_mock_lookup():
    out = handle_mcp(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "lookup_metric",
                "arguments": {"company_code": "002594", "concept": "revenue", "year": 2024},
                "_meta": {"backend": "mock", "request_id": "rid-1"},
            },
        },
        request_id="rid-1",
    )
    structured = out.result["structuredContent"]
    assert structured["ok"] is True
    assert structured["request_id"] == "rid-1"
    assert out.result["isError"] is False


def test_tools_call_unauthorized_is_tool_error_not_rpc_error():
    out = handle_mcp(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "lookup_metric",
                "arguments": {"company_code": "000333", "concept": "revenue", "year": 2024},
                "_meta": {"backend": "mock", "dept": "research"},
            },
        }
    )
    assert out.error is None
    structured = out.result["structuredContent"]
    assert structured["error_code"] == "unauthorized"
    assert out.result["isError"] is True


@pytest.mark.anyio
async def test_mcp_http_client_loop(client: AsyncClient):
    mcp = McpHttpClient(client, request_id="e2e-1", backend="mock", dept="compliance")
    info = await mcp.initialize()
    assert info["protocolVersion"]
    tools = await mcp.list_tools()
    assert {item["name"] for item in tools} >= {"lookup_metric", "list_scope", "verify_number"}
    hit = await mcp.call_tool(
        "lookup_metric",
        {"company_code": "002594", "concept": "revenue", "year": 2024},
    )
    assert hit.ok is True
    assert hit.request_id == "e2e-1"


@pytest.mark.anyio
async def test_mcp_http_unknown_method(client: AsyncClient):
    mcp = McpHttpClient(client)
    with pytest.raises(McpClientError) as exc:
        await mcp._rpc("agents/run")
    assert exc.value.code == METHOD_NOT_FOUND
