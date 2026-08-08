import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_llm_client_dep
from app.main import app
from app.models.base import ChatResult, LLMClient


class FakeLLMClient(LLMClient):
    async def chat(self, messages, *, temperature=0.1) -> str:
        return "这是 mock 回复"

    async def chat_with_usage(self, messages, *, temperature=0.1) -> ChatResult:
        return ChatResult(content="这是 mock 回复", prompt_tokens=1, completion_tokens=2)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    app.dependency_overrides[get_llm_client_dep] = lambda: FakeLLMClient()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


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


@pytest.mark.anyio
async def test_chat_rejects_empty_message(client: AsyncClient):
    response = await client.post("/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_models(client: AsyncClient):
    response = await client.get("/models")
    assert response.status_code == 200
    assert "available" in response.json()
