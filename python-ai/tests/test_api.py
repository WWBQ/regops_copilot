import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.base import ChatResult, LLMClient


class FakeLLMClient(LLMClient):
    async def chat(self, messages, *, temperature=0.1) -> str:
        return "这是 mock 回复"

    async def chat_with_usage(self, messages, *, temperature=0.1) -> ChatResult:
        return ChatResult(
            content="这是 mock 回复",
            prompt_tokens=12,
            completion_tokens=8,
            latency_ms=256.0,
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def client(monkeypatch):
    fake = FakeLLMClient()
    monkeypatch.setattr("app.api.chat.get_llm_client", lambda settings, model=None: fake)
    monkeypatch.setattr("app.api.chat.list_available_models", lambda settings=None: ["deepseek"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_chat(client: AsyncClient):
    response = await client.post("/chat", json={"message": "你好"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "这是 mock 回复"
    assert "disclaimer" in body
    assert body["total_tokens"] == 20
    assert body["latency_ms"] == 256.0


@pytest.mark.anyio
async def test_chat_rejects_empty_message(client: AsyncClient):
    response = await client.post("/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_models(client: AsyncClient):
    response = await client.get("/models")
    assert response.status_code == 200
    assert "available" in response.json()
