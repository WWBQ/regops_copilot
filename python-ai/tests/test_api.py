import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.llm import ChatResult, LLMClient


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
    monkeypatch.setattr("app.chat.router.get_llm_client", lambda settings, model=None: fake)
    monkeypatch.setattr("app.chat.router.list_available_models", lambda settings=None: ["deepseek-flash"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_agent_endpoints_are_not_registered(client: AsyncClient):
    for method, path in (("GET", "/tools"), ("POST", "/tools/invoke"), ("POST", "/mcp")):
        response = await client.request(method, path)
        assert response.status_code == 404


@pytest.mark.anyio
async def test_chat(client: AsyncClient):
    response = await client.post("/chat", json={"message": "你好"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "这是 mock 回复"
    assert "disclaimer" in body
    assert body["total_tokens"] == 20
    assert body["latency_ms"] == 256.0
    assert body["route"] == "chitchat"


@pytest.mark.anyio
async def test_chat_asknum_skips_llm(client: AsyncClient, monkeypatch):
    from app.asknum.lookup import AsknumResult

    from app.asknum.citations import AsknumCite

    monkeypatch.setattr(
        "app.chat.router.try_answer",
        lambda _question, **_kwargs: AsknumResult(
            route="metric",
            reply="比亚迪 2024 年营业收入为 1.00 元 [1]。",
            citations=(
                AsknumCite(
                    doc_id="002594_2024",
                    page=1,
                    snippet="财务事实库",
                    title="财务事实库 · 比亚迪 营业收入",
                    href="/quality/facts?company_code=002594&concept=revenue",
                    kind="facts",
                ),
            ),
        ),
    )
    response = await client.post(
        "/chat",
        json={"message": "比亚迪2024年营收多少", "use_rag": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert "[1]" in body["reply"]
    assert body["route"] == "metric"
    assert body["rag_used"] is False
    assert body["total_tokens"] == 0
    assert body["citations"][0]["kind"] == "facts"
    assert body["citations"][0]["href"] == "/quality/facts?company_code=002594&concept=revenue"


@pytest.mark.anyio
async def test_chat_rejects_empty_message(client: AsyncClient):
    response = await client.post("/chat", json={"message": ""})
    assert response.status_code == 422


def _sse_body(text: str) -> dict[str, str]:
    events: dict[str, str] = {}
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events[event] = "\n".join(data_lines)
    return events


@pytest.mark.anyio
async def test_chat_stream_chitchat(client: AsyncClient):
    async with client.stream("POST", "/chat/stream", json={"message": "你好", "use_rag": False}) as response:
        assert response.status_code == 200
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
    events = _sse_body(body)
    assert "这是 mock 回复" in events.get("delta", "")
    done = json.loads(events["done"])
    assert done["reply"] == "这是 mock 回复"
    assert done["route"] == "general"
    assert done["total_tokens"] == 20


@pytest.mark.anyio
async def test_chat_stream_asknum(client: AsyncClient, monkeypatch):
    from app.asknum.citations import AsknumCite
    from app.asknum.lookup import AsknumResult

    monkeypatch.setattr(
        "app.chat.router.try_answer",
        lambda _question, **_kwargs: AsknumResult(
            route="metric",
            reply="比亚迪 2024 年营业收入为 1.00 元 [1]。",
            citations=(
                AsknumCite(
                    doc_id="002594_2024",
                    page=1,
                    snippet="财务事实库",
                    title="财务事实库 · 比亚迪 营业收入",
                    href="/quality/facts?company_code=002594&concept=revenue",
                    kind="facts",
                ),
            ),
        ),
    )
    async with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "比亚迪2024年营收多少", "use_rag": True},
    ) as response:
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
    events = _sse_body(body)
    done = json.loads(events["done"])
    assert done["route"] == "metric"
    assert "[1]" in done["reply"]
    assert done["total_tokens"] == 0


@pytest.mark.anyio
async def test_chat_rag_blocks_unbacked_amount(client: AsyncClient, monkeypatch):
    from app.chat.router import LlmTurn
    from app.models.llm import ChatResult, LLMClient
    from app.chat.schemas import Citation

    class InventLLM(LLMClient):
        async def chat(self, messages, *, temperature=0.1) -> str:
            return "研发投入约 542 亿元。"

        async def chat_with_usage(self, messages, *, temperature=0.1) -> ChatResult:
            return ChatResult(content="研发投入约 542 亿元。", prompt_tokens=8, completion_tokens=6, latency_ms=10.0)

    monkeypatch.setattr("app.chat.router.get_llm_client", lambda settings, model=None: InventLLM())
    monkeypatch.setattr("app.chat.router.try_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.chat.router._prepare_llm_turn",
        lambda *_args, **_kwargs: LlmTurn(
            messages=[{"role": "user", "content": "风险因素"}],
            citations=[
                Citation(doc_id="002594_2024", page=12, snippet="风险因素包括市场竞争。", title="年报"),
            ],
            rag_used=True,
            route="rag",
        ),
    )
    response = await client.post(
        "/chat",
        json={"message": "比亚迪2024年风险因素有哪些", "use_rag": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag_blocked"
    assert "【数字校验拦截】" in body["reply"]
    assert "〔无证据〕" in body["reply"]
    assert body["validation_trace"][0]["name"] == "number_check"


@pytest.mark.anyio
async def test_models(client: AsyncClient):
    response = await client.get("/models")
    assert response.status_code == 200
    assert "available" in response.json()
