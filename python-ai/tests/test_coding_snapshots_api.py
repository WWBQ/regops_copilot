from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.dependencies import get_object_store, get_settings_dep
from app.main import app
from app.security.service_auth import require_service_token
from app.storage.local import LocalObjectStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path):
    app.dependency_overrides.pop(require_service_token, None)
    store = LocalObjectStore(
        tmp_path / "objects", default_bucket="regops-docs",
        public_base_url="http://test", presign_secret="secret",
    )
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        service_token="test-token", object_store_bucket="regops-docs", _env_file=None,
    )
    app.dependency_overrides[get_object_store] = lambda: store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, store
    app.dependency_overrides.pop(get_settings_dep, None)
    app.dependency_overrides.pop(get_object_store, None)


def archive_of(name: str = "workspace/app.py") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(name, "print(1)")
    return output.getvalue()


@pytest.mark.anyio
async def test_snapshot_round_trip_is_private(client):
    http, store = client
    thread_id = f"{uuid.uuid4()}_coding_{uuid.uuid4()}"
    path = f"/internal/coding-snapshots/{thread_id}"
    body = archive_of()
    assert (await http.put(path, content=body)).status_code == 401
    auth = {"X-Regops-Service-Token": "test-token"}
    saved = await http.put(path, content=body, headers=auth)
    assert saved.status_code == 200
    assert saved.json()["key"] == f"coding-snapshots/{thread_id}.zip"
    assert saved.json()["object_uri"] == f"object://regops-docs/coding-snapshots/{thread_id}.zip"
    assert store.object_exists("regops-docs", saved.json()["key"])
    downloaded = await http.get(path, headers=auth)
    assert downloaded.status_code == 200
    assert downloaded.content == body
    assert downloaded.headers["x-content-sha256"] == saved.json()["sha256"]
    assert (await http.delete(path, headers=auth)).status_code == 204
    assert (await http.get(path, headers=auth)).status_code == 404


@pytest.mark.anyio
async def test_snapshot_rejects_invalid_ids_and_unsafe_zip(client):
    http, _store = client
    auth = {"X-Regops-Service-Token": "test-token"}
    thread_id = f"{uuid.uuid4()}_coding_{uuid.uuid4()}"
    path = f"/internal/coding-snapshots/{thread_id}"
    assert (await http.put(path, content=archive_of("workspace/../escape"), headers=auth)).status_code == 422
    assert (await http.put(path, content=b"not a ZIP", headers=auth)).status_code == 422
    assert (await http.put("/internal/coding-snapshots/not-a-thread", content=archive_of(), headers=auth)).status_code == 422
