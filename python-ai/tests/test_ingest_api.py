from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_document_service, get_object_store, get_settings_dep
from app.config import Settings
from app.documents.service import DocumentService
from app.ingest.pipeline import IngestResult
from app.main import app
from app.storage.local import LocalObjectStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def ingest_client(tmp_path: Path, document_repository_stub):
    root = tmp_path / "objects"
    store = LocalObjectStore(
        root,
        default_bucket="regops-docs",
        public_base_url="http://test",
        presign_secret="test-secret",
    )
    service = DocumentService(store, default_bucket="regops-docs")
    settings = Settings(
        object_store_root=str(root),
        object_store_bucket="regops-docs",
        api_public_base_url="http://test",
        object_store_presign_secret="test-secret",
    )
    app.dependency_overrides[get_document_service] = lambda: service
    app.dependency_overrides[get_object_store] = lambda: store
    app.dependency_overrides[get_settings_dep] = lambda: settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_post_ingest_sync_runs_pipeline(ingest_client: AsyncClient, monkeypatch):
    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.ingest.router.get_connection", fake_conn)
    monkeypatch.setattr(
        "app.ingest.router.create_job",
        lambda *_a, **_k: "11111111-1111-1111-1111-111111111111",
    )

    def fake_ingest(pdf_path, **kwargs):
        assert kwargs["doc_id"] == "002594_2024"
        assert kwargs["job_id"] == "11111111-1111-1111-1111-111111111111"
        assert kwargs["parser_backend"] == "mineru"
        assert Path(pdf_path).is_file()
        return IngestResult(
            doc_id="002594_2024",
            pages=3,
            chunks=9,
            deleted_chunks=0,
            parse_cached=True,
            job_id=kwargs["job_id"],
            parser_backend=kwargs["parser_backend"],
        )

    monkeypatch.setattr("app.ingest.router.ingest_pdf_to_vectors", fake_ingest)
    files = {"file": ("002594_2024.pdf", b"%PDF-1.4 demo", "application/pdf")}
    response = await ingest_client.post(
        "/ingest",
        files=files,
        data={"doc_id": "002594_2024", "sync": "true", "parser_backend": "mineru"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "11111111-1111-1111-1111-111111111111"
    assert body["doc_id"] == "002594_2024"
    assert body["status"] == "DONE"
    assert body["pages"] == 3
    assert body["chunks"] == 9
    assert body["parser_backend"] == "mineru"


@pytest.mark.anyio
async def test_post_ingest_requires_file_or_doc_id(ingest_client: AsyncClient):
    response = await ingest_client.post("/ingest", data={"sync": "true"})
    assert response.status_code == 400


@pytest.mark.anyio
async def test_get_ingest_job_not_found(monkeypatch):
    monkeypatch.setattr("app.ops.ingest_service.get_ingest_job", lambda _job_id: None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ops/ingest/jobs/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 404
