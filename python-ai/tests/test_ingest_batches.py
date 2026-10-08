from __future__ import annotations

import pytest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock
from httpx import ASGITransport, AsyncClient

from app.main import app

from app.db.ingest_job_repository import batch_status


@pytest.mark.parametrize(
    ("active", "done", "failed", "expected"),
    [(0, 0, 0, "QUEUED"), (1, 0, 0, "RUNNING"), (0, 1, 0, "RUNNING"),
     (0, 2, 0, "DONE"), (0, 1, 1, "PARTIAL"), (0, 0, 2, "FAILED")],
)
def test_batch_status(active, done, failed, expected):
    assert batch_status(total=2, active=active, done=done, failed=failed) == expected


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_batch_monitor_passes_filters_to_repository(monkeypatch):
    from app.ops import ingest_service

    calls = []

    def fake_list(**values):
        calls.append(values)
        return {"total": 0, "limit": values["limit"], "offset": values["offset"], "items": []}

    monkeypatch.setattr(ingest_service, "list_ingest_batches", fake_list)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/ops/ingest/batches",
            params={"status": "FAILED", "parser_backend": "mineru", "keyword": "002594"},
        )
    assert response.status_code == 200
    assert calls == [{
        "limit": 20, "offset": 0, "status": "FAILED",
        "parser_backend": "mineru", "keyword": "002594",
    }]


def test_worker_continues_after_one_file_fails(monkeypatch):
    from app.ingest import tasks

    jobs = [
        ("j1", "first", "PENDING", True, "docling"),
        ("j2", "second", "PENDING", True, "docling"),
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value = jobs

    @contextmanager
    def fake_conn():
        yield conn

    service = MagicMock()
    service.local_pdf_path.side_effect = lambda doc_id: Path(f"/{doc_id}.pdf")
    processed = []
    failed = []

    def fake_ingest(_path, **values):
        processed.append(values["doc_id"])
        if values["doc_id"] == "first":
            raise ValueError("invalid PDF")

    monkeypatch.setattr(tasks, "get_connection", fake_conn)
    monkeypatch.setattr(tasks, "_build_document_service", lambda: service)
    monkeypatch.setattr(tasks, "ingest_pdf_to_vectors", fake_ingest)
    monkeypatch.setattr(tasks, "_fail_job", lambda job_id, error: failed.append((job_id, str(error))))

    tasks.process_ingest_batch.run("11111111-1111-1111-1111-111111111111")
    assert processed == ["first", "second"]
    assert failed == [("j1", "invalid PDF")]


def test_retry_failed_batch_resets_only_failed_files(monkeypatch):
    from app.db import ingest_job_repository as repository

    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ("PARTIAL",)
    cursor.fetchall.return_value = [("failed-job-id",)]
    snapshots = []
    monkeypatch.setattr(repository, "record_batch_snapshot", lambda *_a, **kwargs: snapshots.append(kwargs))

    assert repository.retry_failed_batch(conn, batch_id="batch-id") == 1
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    assert "status = 'FAILED'" in queries[1]
    assert "retry_count = retry_count + 1" in queries[1]
    assert "finished_at = NULL" in queries[1]
    assert snapshots == [{"batch_id": "batch-id", "stage": "RETRY"}]


def test_retry_rejects_nonterminal_batch():
    from app.db.ingest_job_repository import retry_failed_batch

    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = ("RUNNING",)
    with pytest.raises(ValueError, match="only failed or partial"):
        retry_failed_batch(conn, batch_id="batch-id")
