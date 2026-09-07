import io
from pathlib import Path

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_label_store, get_llm_client_dep
from app.labeling.store import LabelStore
from app.main import app
from app.models.base import ChatResult, LLMClient


class FakeLLMClient(LLMClient):
    async def chat(self, messages, *, temperature=0.1) -> str:
        return "这是 mock 回复"

    async def chat_with_usage(self, messages, *, temperature=0.1, tools=None) -> ChatResult:
        return ChatResult(content="这是 mock 回复", prompt_tokens=1, completion_tokens=2)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path):
    store = LabelStore(tmp_path)
    app.dependency_overrides[get_label_store] = lambda: store
    app.dependency_overrides[get_llm_client_dep] = lambda: FakeLLMClient()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _xlsx_bytes(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


@pytest.mark.anyio
async def test_create_and_list_tasks(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            _xlsx_bytes([{"id": "1", "url": "https://example.com/a.pdf", "text": "hello"}]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    created = await client.post(
        "/labeling/tasks",
        data={"name": "年报抽检", "desc": "demo", "url_type": "text"},
        files=files,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "年报抽检"
    assert body["url_type"] == "text"
    assert body["label_options"] == ["OK", "有问题", "跳过"]
    assert body["count"] == 1
    assert body["progress"] == 0

    listed = await client.get("/labeling/tasks")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]


@pytest.mark.anyio
async def test_create_rejects_missing_url_column(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            _xlsx_bytes([{"title": "no url"}]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post(
        "/labeling/tasks",
        data={"name": "bad", "url_type": "pdf"},
        files=files,
    )
    assert resp.status_code == 400
    assert "必填列" in resp.json()["detail"] or "url" in resp.json()["detail"]


@pytest.mark.anyio
async def test_save_item_and_export(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            _xlsx_bytes(
                [
                    {"id": "a", "url": "https://example.com/a.pdf", "text": "原文"},
                    {"id": "b", "url": "https://example.com/b.pdf", "text": "第二"},
                ]
            ),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    created = await client.post(
        "/labeling/tasks",
        data={"name": "export-demo", "url_type": "html"},
        files=files,
    )
    task_id = created.json()["id"]

    detail = await client.get(f"/labeling/tasks/{task_id}")
    assert detail.status_code == 200
    assert len(detail.json()["items"]) == 2
    assert detail.json()["items"][0]["type"] == "html"

    item = await client.get(f"/labeling/tasks/{task_id}/items/0")
    assert item.status_code == 200
    assert item.json()["total"] == 2

    missing = await client.get(f"/labeling/tasks/{task_id}/items/9")
    assert missing.status_code == 404

    saved = await client.post(
        f"/labeling/tasks/{task_id}/items/0",
        json={"status": "OK", "notes": "通过", "text": "改正文"},
    )
    assert saved.status_code == 200
    assert saved.json()["progress"] == 50
    assert saved.json()["saved"]["text"] == "改正文"

    exported = await client.get(f"/labeling/tasks/{task_id}/export")
    assert exported.status_code == 200
    assert "spreadsheetml" in exported.headers["content-type"]


@pytest.mark.anyio
async def test_create_custom_label_options(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            _xlsx_bytes([{"id": "1", "url": "https://example.com/a.pdf", "text": "hello"}]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    created = await client.post(
        "/labeling/tasks",
        data={
            "name": "自定义选项",
            "url_type": "text",
            "label_options": '["通过", "不通过", "待定"]',
        },
        files=files,
    )
    assert created.status_code == 200, created.text
    assert created.json()["label_options"] == ["通过", "不通过", "待定"]
    task_id = created.json()["id"]

    item = await client.get(f"/labeling/tasks/{task_id}/items/0")
    assert item.json()["label_options"] == ["通过", "不通过", "待定"]

    rejected = await client.post(
        f"/labeling/tasks/{task_id}/items/0",
        json={"status": "ok"},
    )
    assert rejected.status_code == 400

    saved = await client.post(
        f"/labeling/tasks/{task_id}/items/0",
        json={"status": "待定"},
    )
    assert saved.status_code == 200
    assert saved.json()["saved"]["status"] == "待定"


@pytest.mark.anyio
async def test_create_rejects_empty_label_options(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            _xlsx_bytes([{"id": "1", "url": "https://example.com/a.pdf", "text": ""}]),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post(
        "/labeling/tasks",
        data={"name": "empty-opts", "url_type": "pdf", "label_options": "[]"},
        files=files,
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_download_template(client: AsyncClient):
    resp = await client.get("/labeling/template")
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


@pytest.mark.anyio
async def test_create_rejects_non_xlsx_bytes(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            b"id,url,text\n1,https://example.com/a.pdf,hello\n",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post(
        "/labeling/tasks",
        data={"name": "csv-as-xlsx", "url_type": "pdf"},
        files=files,
    )
    assert resp.status_code == 400
    assert "xlsx" in resp.json()["detail"]


@pytest.mark.anyio
async def test_create_rejects_duplicate_id(client: AsyncClient):
    files = {
        "file": (
            "data.xlsx",
            _xlsx_bytes(
                [
                    {"id": "dup", "url": "https://example.com/a.pdf", "text": "a"},
                    {"id": "dup", "url": "https://example.com/b.pdf", "text": "b"},
                ]
            ),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = await client.post(
        "/labeling/tasks",
        data={"name": "dup", "url_type": "text"},
        files=files,
    )
    assert resp.status_code == 400
    assert "重复" in resp.json()["detail"]

