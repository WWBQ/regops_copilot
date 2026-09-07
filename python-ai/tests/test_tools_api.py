import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.tools import LookupMetricArgs, LookupMetricResult


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_list_tools_catalog(client: AsyncClient):
    response = await client.get("/tools")
    assert response.status_code == 200
    body = response.json()
    assert body["transport"] == "function_calling"
    assert body["mcp"]["endpoint"] == "/mcp"
    assert "tools/list" in body["mcp"]["methods"]
    assert body["wired_to_chat"] is True
    assert body["chat_entry"] == "intent"
    assert body["wired_to_graph"] is True
    names = [item["name"] for item in body["tools"]]
    assert "lookup_metric" in names
    assert "verify_number" in names
    assert "execute_sql" not in names


@pytest.mark.anyio
async def test_invoke_lookup_via_api(client: AsyncClient, monkeypatch):
    def fake_run(args: LookupMetricArgs) -> LookupMetricResult:
        return LookupMetricResult(
            ok=True,
            stop=False,
            outcome="ok",
            company_code=args.company_code,
            concept=args.concept,
            year=args.year,
            scope=args.scope,
            value_yuan="1.00",
            message="ok",
        )

    monkeypatch.setattr("app.tools.registry.run_lookup_metric", fake_run)
    response = await client.post(
        "/tools/invoke",
        json={
            "name": "lookup_metric",
            "arguments": {"company_code": "002594", "concept": "revenue", "year": 2024},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["result"]["value_yuan"] == "1.00"


@pytest.mark.anyio
async def test_capabilities_and_schema(client: AsyncClient):
    caps = await client.get("/tools/capabilities")
    assert caps.status_code == 200
    body = caps.json()
    names = {item["name"] for item in body["commands"]}
    assert "lookup_metric" in names
    assert "create_review_draft" in names
    assert "execute_sql" in body["forbidden"]
    schema = await client.get("/tools/schema/lookup_metric")
    assert schema.status_code == 200
    assert schema.json()["name"] == "lookup_metric"
    missing = await client.get("/tools/schema/execute_sql")
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_service_token_required_only_when_service_header_present(
    client: AsyncClient, monkeypatch
):
    class _Settings:
        service_token = "secret-token"

    monkeypatch.setattr("app.security.service_identity.get_settings", lambda: _Settings())
    rejected = await client.post(
        "/tools/invoke",
        headers={"X-Regops-Service": "java-service", "X-Regops-Service-Token": "wrong"},
        json={"name": "lookup_metric", "arguments": {"company_code": "002594", "concept": "revenue", "year": 2024}},
    )
    assert rejected.status_code == 401
    allowed = await client.post(
        "/tools/invoke",
        json={"name": "execute_sql", "arguments": {}},
    )
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is False


@pytest.mark.anyio
async def test_invoke_unknown_tool(client: AsyncClient):
    response = await client.post(
        "/tools/invoke",
        json={"name": "execute_sql", "arguments": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["stop"] is True
