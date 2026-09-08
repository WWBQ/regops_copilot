import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_echoes_incoming_request_id(client: AsyncClient):
    response = await client.get("/health", headers={"X-Request-ID": "demo-w9-1"})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "demo-w9-1"
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_health_mints_request_id_when_missing(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    minted = response.headers.get("x-request-id")
    assert minted
    uuid.UUID(minted)


@pytest.mark.anyio
async def test_health_echoes_incoming_traceparent(client: AsyncClient):
    traceparent = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    response = await client.get("/health", headers={"traceparent": traceparent})
    assert response.status_code == 200
    assert response.headers.get("traceparent") == traceparent


@pytest.mark.anyio
async def test_health_mints_traceparent_when_missing(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    minted = response.headers.get("traceparent")
    assert minted
    assert minted.startswith("00-")
    assert len(minted.split("-")) == 4
