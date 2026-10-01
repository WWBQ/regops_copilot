from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.dependencies import get_settings_dep
from app.main import app
from app.security.service_auth import require_service_token


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def secured_client():
    app.dependency_overrides.pop(require_service_token, None)
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        service_token="expected-service-token",
        _env_file=None,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.pop(get_settings_dep, None)


@pytest.mark.anyio
async def test_health_is_public(secured_client: AsyncClient):
    response = await secured_client.get("/health")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_presigned_storage_route_uses_signature_instead_of_service_token(
    secured_client: AsyncClient,
):
    response = await secured_client.get("/storage/objects/regops-docs/reports/demo.pdf")
    assert response.status_code == 422


@pytest.mark.anyio
async def test_protected_api_rejects_missing_service_token(secured_client: AsyncClient):
    response = await secured_client.get("/models")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid service credentials"}


@pytest.mark.anyio
async def test_protected_api_rejects_wrong_service_token(secured_client: AsyncClient):
    response = await secured_client.get(
        "/models",
        headers={"X-Regops-Service-Token": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_protected_api_accepts_matching_service_token(secured_client: AsyncClient):
    response = await secured_client.get(
        "/models",
        headers={"X-Regops-Service-Token": "expected-service-token"},
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_missing_server_configuration_fails_closed():
    app.dependency_overrides.pop(require_service_token, None)
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        service_token="",
        _env_file=None,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/models",
                headers={"X-Regops-Service-Token": "anything"},
            )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.pop(get_settings_dep, None)
