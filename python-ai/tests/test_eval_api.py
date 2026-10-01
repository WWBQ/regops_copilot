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
    assert "w4_asknum" in ids
    assert "w6_number_check" in ids
    assert "w8_strategy" in ids
    assert "w8_ab" in ids
    assert "rag_acl" in ids
    assert "rag_refuse" in ids
    assert "rag_support" in ids
    assert "rag_compare" in ids
    asknum = next(item for item in body["items"] if item["id"] == "w4_asknum")
    assert "leak_rate" in asknum["metrics"]
    numbers = next(item for item in body["items"] if item["id"] == "w6_number_check")
    assert "number_error_rate" in numbers["metrics"]
    assert "unit_error_rate" in numbers["metrics"]
    strategy = next(item for item in body["items"] if item["id"] == "w8_strategy")
    assert "number_error_rate" in strategy["metrics"]
    ab = next(item for item in body["items"] if item["id"] == "w8_ab")
    assert "credible" in ab["metrics"]
    retrieval = next(item for item in body["items"] if item["id"] == "rag_retrieval")
    assert "ndcg_at_k" in retrieval["metrics"]
    assert "citation_accuracy" in retrieval["metrics"]
    acl = next(item for item in body["items"] if item["id"] == "rag_acl")
    assert "leak_rate" in acl["metrics"]
    refuse = next(item for item in body["items"] if item["id"] == "rag_refuse")
    assert "false_accept_rate" in refuse["metrics"]
    support = next(item for item in body["items"] if item["id"] == "rag_support")
    assert "support_hit_rate" in support["metrics"]
    comparison = next(item for item in body["items"] if item["id"] == "rag_compare")
    assert "company_scope_accuracy" in comparison["metrics"]
    assert "false_compare_rate" in comparison["metrics"]
    w1 = next(item for item in body["items"] if item["id"] == "w1_chat")
    assert "refuse_rate" in w1["metrics"]
    assert "number_error_rate" not in w1["metrics"]


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
async def test_preview_w1_golden_set():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/eval/golden-sets/w1_chat_30.json")
    assert response.status_code == 200
    body = response.json()
    assert body["item_count"] == 30
    assert "accounting" in body["categories"]
    assert body["items"][0]["id"] == "w1-001"
    assert body["items"][0]["question"]


@pytest.mark.anyio
async def test_start_w1_chat_rejects_empty_selection(monkeypatch):
    monkeypatch.setattr(
        "app.eval.job_service.list_available_models",
        lambda settings=None: ["deepseek", "qwen"],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/ops/eval/runs",
            json={"task_id": "w1_chat", "model": "deepseek", "categories": ["not-a-category"]},
        )
    assert response.status_code == 400
    assert "没有匹配的评测题" in response.json()["detail"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/ops/eval/runs/does-not-exist")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_start_w1_chat_rejects_unknown_model(monkeypatch):
    monkeypatch.setattr(
        "app.eval.job_service.list_available_models",
        lambda settings=None: ["deepseek", "qwen"],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/ops/eval/runs",
            json={"task_id": "w1_chat", "model": "not-a-model", "limit": 1},
        )
    assert response.status_code == 400
    assert "unsupported model" in response.json()["detail"]


@pytest.mark.anyio
async def test_models_includes_default():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/models")
    assert response.status_code == 200
    body = response.json()
    assert "available" in body
    assert "default" in body
