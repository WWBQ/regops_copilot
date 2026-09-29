from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_document_service, get_object_store, get_settings_dep
from app.config import Settings
from app.documents.registry import DocumentRegistry
from app.documents.service import DocumentService
from app.main import app
from app.storage.local import LocalObjectStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def document_env(tmp_path: Path):
    root = tmp_path / "objects"
    store = LocalObjectStore(
        root,
        default_bucket="regops-docs",
        public_base_url="http://test",
        presign_secret="test-secret",
    )
    registry = DocumentRegistry(root / "_registry" / "documents.json")
    service = DocumentService(store, registry, default_bucket="regops-docs")
    settings = Settings(
        object_store_root=str(root),
        object_store_bucket="regops-docs",
        api_public_base_url="http://test",
        object_store_presign_secret="test-secret",
    )
    return store, service, settings


@pytest.fixture
async def doc_client(document_env):
    store, service, settings = document_env
    app.dependency_overrides[get_document_service] = lambda: service
    app.dependency_overrides[get_object_store] = lambda: store
    app.dependency_overrides[get_settings_dep] = lambda: settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_upload_and_viewer_url(doc_client: AsyncClient):
    files = {"file": ("002594_2024_annual.pdf", b"%PDF-1.4 demo content", "application/pdf")}
    upload = await doc_client.post("/documents/upload", files=files, data={"doc_id": "002594_2024"})
    assert upload.status_code == 200
    body = upload.json()
    assert body["doc_id"] == "002594_2024"
    assert body["bucket"] == "regops-docs"
    assert body["object_key"].startswith("reports/002594_2024/sha256:")
    assert body["reused"] is False

    viewer = await doc_client.get("/documents/002594_2024/viewer-url", params={"page": 42, "expires_in": 300})
    assert viewer.status_code == 200
    viewer_body = viewer.json()
    assert viewer_body["page"] == 42
    assert "#page=42" in viewer_body["viewer_url"]

    fetch = await doc_client.get(viewer_body["viewer_url"].replace("http://test", ""))
    assert fetch.status_code == 200
    assert fetch.content.startswith(b"%PDF")
    assert "inline" in fetch.headers.get("content-disposition", "")


@pytest.mark.anyio
async def test_document_content_inline(doc_client: AsyncClient):
    files = {"file": ("002594_2024_annual.pdf", b"%PDF-1.4 inline preview", "application/pdf")}
    upload = await doc_client.post("/documents/upload", files=files, data={"doc_id": "002594_2024"})
    assert upload.status_code == 200

    response = await doc_client.get("/documents/002594_2024/content")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-type"] == "application/pdf"
    assert "inline" in response.headers.get("content-disposition", "")


@pytest.mark.anyio
async def test_upload_idempotent(doc_client: AsyncClient):
    payload = b"%PDF-same-file"
    files = {"file": ("002594_2024_annual.pdf", payload, "application/pdf")}
    first = await doc_client.post("/documents/upload", files=files, data={"doc_id": "002594_2024"})
    second = await doc_client.post("/documents/upload", files=files, data={"doc_id": "002594_2024"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert first.json()["content_hash"] == second.json()["content_hash"]


@pytest.mark.anyio
async def test_storage_rejects_unsigned(doc_client: AsyncClient):
    response = await doc_client.get("/storage/objects/regops-docs/reports/x.pdf")
    assert response.status_code == 422
