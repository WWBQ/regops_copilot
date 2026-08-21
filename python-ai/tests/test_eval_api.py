"""Eval API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_list_eval_tasks():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/eval/tasks")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    ids = {item["id"] for item in body["items"]}
    assert "w1_chat" in ids
    assert "rag_retrieval" in ids


@pytest.mark.anyio
async def test_list_golden_sets():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/eval/golden-sets")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "runners" in body


@pytest.mark.anyio
async def test_create_and_delete_custom_task():
    task_id = "test_custom_task"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/ops/eval/tasks",
            json={
                "id": task_id,
                "name": "测试任务",
                "description": "单元测试",
                "golden_file": "w1_chat_30.json",
                "runner": "w1_chat",
            },
        )
        assert create.status_code == 200
        assert create.json()["id"] == task_id

        delete = await client.delete(f"/ops/eval/tasks/{task_id}")
        assert delete.status_code == 200


@pytest.mark.anyio
async def test_cannot_delete_builtin_task():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/ops/eval/tasks/w1_chat")
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_golden_set():
    payload = {
        "version": "test-v1",
        "items": [
            {
                "id": "t-001",
                "question": "测试问题",
                "doc_id": "002594_2024",
                "gold_pages": [3],
            }
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/ops/eval/golden-sets/upload",
            json={"filename": "test_upload_set.json", "content": payload, "runner": "rag_retrieval"},
        )
    assert response.status_code == 200
    assert response.json()["item_count"] == 1
    # cleanup
    from app.eval.registry import GOLDEN_DIR

    path = GOLDEN_DIR / "test_upload_set.json"
    if path.exists():
        path.unlink()


@pytest.mark.anyio
async def test_delete_run_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/ops/eval/runs/does-not-exist")
    assert response.status_code == 404
