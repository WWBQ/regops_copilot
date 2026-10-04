"""MCP HTTP 边界：令牌校验与只读工具发现。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.mcp import http as mcp_http


def test_financial_mcp_requires_service_token_and_exposes_only_two_tools(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(startup_warmup_enabled=False))
    monkeypatch.setattr(mcp_http, "get_settings", lambda: SimpleNamespace(service_token="test-service-token"))

    with TestClient(main.app) as client:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
        }
        assert client.post("/mcp/", json=request, headers=headers).status_code == 401
        authorized = client.post(
            "/mcp/", json=request,
            headers={**headers, "X-Regops-Service-Token": "test-service-token"},
        )
        assert authorized.status_code == 200
        assert {tool["name"] for tool in authorized.json()["result"]["tools"]} == {
            "lookup_financial_facts", "search_report_evidence",
        }
