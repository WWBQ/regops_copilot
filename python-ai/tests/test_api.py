import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.base import ChatResult, LLMClient


class FakeLLMClient(LLMClient):
    async def chat(self, messages, *, temperature=0.1) -> str:
        return "这是 mock 回复"

    async def chat_with_usage(self, messages, *, temperature=0.1, tools=None) -> ChatResult:
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
    assert body["route"] == "chitchat"


@pytest.mark.anyio
async def test_chat_asknum_skips_llm(client: AsyncClient, monkeypatch):
    from app.asknum.lookup import AsknumResult

    from app.asknum.citations import AsknumCite

    monkeypatch.setattr(
        "app.api.chat.try_answer",
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
async def test_chat_review_graph_skips_asknum(client: AsyncClient, monkeypatch):
    from app.agents.graph import WorkflowResult
    from app.schemas.chat import Citation

    def boom(*_args, **_kwargs):
        raise AssertionError("asknum should not run for review graph")

    monkeypatch.setattr("app.api.chat.try_answer", boom)
    monkeypatch.setattr(
        "app.api.chat.run_review_workflow",
        lambda _question, **_kwargs: WorkflowResult(
            route="agent_paused",
            reply="工作流已暂停",
            citations=[
                Citation(doc_id="002594_2024", page=20, snippet="管理层讨论", kind="document"),
            ],
            rag_used=True,
            trace=[{"node": "classify"}, {"node": "checkpoint"}],
            thread_id="public:11111111-1111-1111-1111-111111111111",
            pending_node="conclude",
        ),
    )
    response = await client.post(
        "/chat",
        json={"message": "对比比亚迪和长城2024年净利润并给出结论", "use_rag": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "agent_paused"
    assert body["thread_id"].startswith("public:")
    assert body["pending_node"] == "conclude"
    assert body["total_tokens"] == 0


@pytest.mark.anyio
async def test_chat_resume_checkpoint_uses_thread_id(client: AsyncClient, monkeypatch):
    from app.agents.graph import WorkflowResult

    captured: dict = {}

    def fake(question, **kwargs):
        captured["question"] = question
        captured.update(kwargs)
        return WorkflowResult(
            route="agent",
            reply="工作流已给出结论",
            thread_id=kwargs.get("thread_id"),
        )

    monkeypatch.setattr("app.api.chat.try_answer", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("asknum")))
    monkeypatch.setattr("app.api.chat.run_review_workflow", fake)
    response = await client.post(
        "/chat",
        json={
            "message": "确认",
            "use_rag": True,
            "thread_id": "public:11111111-1111-1111-1111-111111111111",
        },
    )
    assert response.status_code == 200
    assert captured["action"] == "resume"
    assert captured["thread_id"] == "public:11111111-1111-1111-1111-111111111111"
    assert response.json()["route"] == "agent"


@pytest.mark.anyio
async def test_chat_tool_loop_skips_asknum(client: AsyncClient, monkeypatch):
    from app.agents.tool_loop import ToolLoopResult

    def boom(*_args, **_kwargs):
        raise AssertionError("asknum should not run for tool loop")

    async def fake_loop(_question, _client, **_kwargs):
        return ToolLoopResult(
            route="tools",
            reply="【工具自选】list_scope\n\n已按工具返回作答",
            rag_used=False,
            prompt_tokens=10,
            completion_tokens=6,
            latency_ms=12.0,
            trace=[{"name": "list_scope", "ok": True}],
        )

    monkeypatch.setattr("app.api.chat.try_answer", boom)
    monkeypatch.setattr("app.api.chat.run_tool_loop", fake_loop)
    response = await client.post(
        "/chat",
        json={"message": "你自己选工具：格力2024年有哪些可查指标", "use_rag": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "tools"
    assert body["total_tokens"] == 16
    assert "工具自选" in body["reply"]


@pytest.mark.anyio
async def test_chat_overview_enters_tool_loop(client: AsyncClient, monkeypatch):
    from app.agents.tool_loop import ToolLoopResult

    def boom(*_args, **_kwargs):
        raise AssertionError("asknum should not run for overview tool loop")

    async def fake_loop(_question, _client, **_kwargs):
        return ToolLoopResult(route="tools", reply="【工具自选】list_scope\n\n概述", trace=[{"name": "list_scope"}])

    monkeypatch.setattr("app.api.chat.try_answer", boom)
    monkeypatch.setattr("app.api.chat.run_tool_loop", fake_loop)
    response = await client.post(
        "/chat",
        json={"message": "格力2024年经营得怎么样", "use_rag": True},
    )
    assert response.status_code == 200
    assert response.json()["route"] == "tools"


@pytest.mark.anyio
async def test_chat_use_rag_false_skips_graph(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.api.chat.run_review_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("graph skipped")),
    )
    response = await client.post(
        "/chat",
        json={"message": "对比比亚迪和长城2024年净利润并给出结论", "use_rag": False},
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "这是 mock 回复"


@pytest.mark.anyio
async def test_chat_use_rag_false_skips_tool_loop(client: AsyncClient, monkeypatch):
    async def fake_loop(*_args, **_kwargs):
        raise AssertionError("tool loop skipped when use_rag=false")

    monkeypatch.setattr("app.api.chat.run_tool_loop", fake_loop)
    response = await client.post(
        "/chat",
        json={"message": "你自己选工具：格力2024年有哪些可查指标", "use_rag": False},
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "这是 mock 回复"


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
        "app.api.chat.try_answer",
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
async def test_chat_stream_tool_loop(client: AsyncClient, monkeypatch):
    from app.agents.tool_loop import ToolLoopResult

    async def fake_loop(_question, _client, **_kwargs):
        on_event = _kwargs.get("on_event")
        if on_event:
            await on_event("status", {"text": "正在查询财务数字…"})
        return ToolLoopResult(route="tools", reply="【工具自选】lookup_metric\n\n概述", trace=[{"name": "lookup_metric"}])

    monkeypatch.setattr("app.api.chat.run_tool_loop", fake_loop)
    async with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "格力2024年经营得怎么样", "use_rag": True},
    ) as response:
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
    events = _sse_body(body)
    assert "正在查询财务数字" in events.get("status", "")
    done = json.loads(events["done"])
    assert done["route"] == "tools"
    assert "工具自选" in done["reply"]


@pytest.mark.anyio
async def test_chat_rag_blocks_unbacked_amount(client: AsyncClient, monkeypatch):
    from app.api.chat import LlmTurn
    from app.models.base import ChatResult, LLMClient
    from app.schemas.chat import Citation

    class InventLLM(LLMClient):
        async def chat(self, messages, *, temperature=0.1) -> str:
            return "研发投入约 542 亿元。"

        async def chat_with_usage(self, messages, *, temperature=0.1, tools=None) -> ChatResult:
            return ChatResult(content="研发投入约 542 亿元。", prompt_tokens=8, completion_tokens=6, latency_ms=10.0)

    monkeypatch.setattr("app.api.chat.get_llm_client", lambda settings, model=None: InventLLM())
    monkeypatch.setattr("app.api.chat.try_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.api.chat._prepare_llm_turn",
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


@pytest.mark.anyio
async def test_models(client: AsyncClient):
    response = await client.get("/models")
    assert response.status_code == 200
    assert "available" in response.json()
