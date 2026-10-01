import json
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.llm import ChatResult, StreamDelta


class FakeLLMClient:
    model_id = "deepseek-flash"

    async def chat_with_usage(self, messages, *, temperature=0.1) -> ChatResult:
        return ChatResult(
            content="这是 mock 回复",
            prompt_tokens=12,
            completion_tokens=8,
            latency_ms=256.0,
        )

    async def chat_stream(self, messages, *, temperature=0.1):
        result = await self.chat_with_usage(messages, temperature=temperature)
        yield StreamDelta(text=result.content)
        yield StreamDelta(done=True, result=result)


def _comparison_json() -> str:
    return json.dumps(
        {
            "answer_type": "company_comparison",
            "comparison_allowed": True,
            "periods": [2024],
            "companies": [
                {
                    "company_code": "002594",
                    "company_name": "比亚迪",
                    "summary": "比亚迪强调供应链韧性。",
                    "citation_ids": [1],
                },
                {
                    "company_code": "601633",
                    "company_name": "长城汽车",
                    "summary": "长城汽车强调供应商协同。",
                    "citation_ids": [2],
                },
            ],
            "similarities": [
                {
                    "statement": "两家公司都关注供应链稳定。",
                    "citation_ids": [1, 2],
                }
            ],
            "differences": [
                {
                    "statement": "两家公司披露的管理重点不同。",
                    "citation_ids": [1, 2],
                }
            ],
            "missing_evidence": [],
        },
        ensure_ascii=False,
    )


class FakeComparisonLLM(FakeLLMClient):
    async def chat_with_usage(self, messages, *, temperature=0.1) -> ChatResult:
        return ChatResult(
            content=_comparison_json(),
            prompt_tokens=40,
            completion_tokens=30,
            latency_ms=50.0,
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def client(monkeypatch):
    fake = FakeLLMClient()
    monkeypatch.setattr("app.chat.router.get_llm_client", lambda settings, model=None: fake)
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
    from app.obs.performance import clear_performance_traces, list_performance_traces

    clear_performance_traces()
    response = await client.post("/chat", json={"message": "你好"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "这是 mock 回复"
    assert "disclaimer" in body
    assert body["total_tokens"] == 20
    assert body["latency_ms"] == 256.0
    assert body["total_latency_ms"] > 0
    assert body["route"] == "chitchat"
    trace = list_performance_traces()["items"][0]
    assert trace["route"] == "chitchat"
    assert trace["timing_ms"]["answer_model"] >= 0
    assert trace["timing_ms"]["total"] == body["total_latency_ms"]
    assert "question" not in trace


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
async def test_chat_asknum_failure_does_not_fall_through_to_rag(
    client: AsyncClient, monkeypatch
):
    monkeypatch.setattr(
        "app.chat.router.try_answer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    prepare_rag = MagicMock()
    monkeypatch.setattr("app.chat.router._prepare_llm_turn", prepare_rag)

    response = await client.post(
        "/chat",
        json={"message": "比亚迪2024年营收多少", "use_rag": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "metric_error"
    assert body["rag_used"] is False
    assert "不会降级为 RAG" in body["reply"]
    prepare_rag.assert_not_called()


@pytest.mark.anyio
async def test_chat_multi_company_metric_stays_in_asknum(
    client: AsyncClient, monkeypatch
):
    from app.asknum.lookup import AsknumResult

    compare_rag = MagicMock()
    monkeypatch.setattr(
        "app.chat.router.try_answer",
        lambda *_args, **_kwargs: AsknumResult(
            route="metric",
            reply="确定性比较：比亚迪高于长城汽车。",
            intent="asknum_compare",
        ),
    )
    monkeypatch.setattr("app.chat.router.prepare_multi_company_rag", compare_rag)

    response = await client.post(
        "/chat",
        json={"message": "比亚迪和长城汽车2024年营业收入谁更高", "use_rag": True},
    )

    assert response.status_code == 200
    assert response.json()["route"] == "metric"
    assert response.json()["rag_used"] is False
    compare_rag.assert_not_called()


@pytest.mark.anyio
async def test_chat_multi_company_rag_uses_gated_comparison_route(
    client: AsyncClient, monkeypatch
):
    from app.rag.comparison import CompanyEvidence, ComparisonPrepareResult
    from app.rag.service import Citation as RagCitation
    from app.rag.service import RagAnswer

    monkeypatch.setattr("app.chat.router.try_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.chat.router.get_llm_client",
        lambda settings, model=None: FakeComparisonLLM(),
    )
    monkeypatch.setattr(
        "app.chat.router.prepare_multi_company_rag",
        lambda **_kwargs: ComparisonPrepareResult(
            answer=RagAnswer(
                messages=[{"role": "user", "content": "按公司隔离后的证据"}],
                citations=[],
                doc_ids=["002594_2024", "601633_2024"],
            ),
            blocked_reply=None,
            citations=(
                RagCitation(
                    doc_id="002594_2024",
                    page=10,
                    snippet="比亚迪供应链风险证据",
                    viewer_url=None,
                    title="比亚迪2024年年度报告",
                ),
                RagCitation(
                    doc_id="601633_2024",
                    page=12,
                    snippet="长城汽车供应链风险证据",
                    viewer_url=None,
                    title="长城汽车2024年年度报告",
                ),
            ),
            selected_years=(2024,),
            evidences=(
                CompanyEvidence("002594", "比亚迪", ("002594_2024",)),
                CompanyEvidence("601633", "长城汽车", ("601633_2024",)),
            ),
        ),
    )

    response = await client.post(
        "/chat",
        json={"message": "比亚迪和长城汽车的供应链风险有哪些差异", "use_rag": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag_compare"
    assert body["rag_used"] is True
    assert body["comparison"]["answer_type"] == "company_comparison"
    assert body["comparison"]["comparison_allowed"] is True
    assert "### 比亚迪" in body["reply"]
    assert {item["doc_id"] for item in body["citations"]} == {
        "002594_2024",
        "601633_2024",
    }


@pytest.mark.anyio
async def test_chat_multi_company_rag_gate_blocks_before_llm(
    client: AsyncClient, monkeypatch
):
    from unittest.mock import AsyncMock

    from app.rag.comparison import CompanyEvidence, ComparisonPrepareResult

    monkeypatch.setattr("app.chat.router.try_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.chat.router.prepare_multi_company_rag",
        lambda **_kwargs: ComparisonPrepareResult(
            answer=None,
            blocked_reply="无法直接比较：长城汽车没有达到相关性阈值的直接证据。",
            citations=(),
            selected_years=(2024,),
            evidences=(
                CompanyEvidence(
                    "601633",
                    "长城汽车",
                    ("601633_2024",),
                    status="low_score",
                    reason="没有达到相关性阈值的直接证据",
                ),
            ),
        ),
    )
    complete = AsyncMock()
    monkeypatch.setattr("app.chat.router._complete_llm", complete)

    response = await client.post(
        "/chat",
        json={"message": "比亚迪和长城汽车的供应链风险有哪些差异", "use_rag": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag_compare_blocked"
    assert "无法直接比较" in body["reply"]
    assert body["total_tokens"] == 0
    complete.assert_not_awaited()


@pytest.mark.anyio
async def test_chat_stream_hides_raw_comparison_json(
    client: AsyncClient, monkeypatch
):
    from app.rag.comparison import CompanyEvidence, ComparisonPrepareResult
    from app.rag.service import Citation as RagCitation
    from app.rag.service import RagAnswer

    monkeypatch.setattr("app.chat.router.try_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.chat.router.get_llm_client",
        lambda settings, model=None: FakeComparisonLLM(),
    )
    monkeypatch.setattr(
        "app.chat.router.prepare_multi_company_rag",
        lambda **_kwargs: ComparisonPrepareResult(
            answer=RagAnswer(
                messages=[{"role": "user", "content": "按公司隔离后的证据"}],
                citations=[],
                doc_ids=["002594_2024", "601633_2024"],
            ),
            blocked_reply=None,
            citations=(
                RagCitation("002594_2024", 10, "比亚迪供应链风险证据", None, "比亚迪年报"),
                RagCitation("601633_2024", 12, "长城汽车供应链风险证据", None, "长城年报"),
            ),
            selected_years=(2024,),
            evidences=(
                CompanyEvidence("002594", "比亚迪", ("002594_2024",)),
                CompanyEvidence("601633", "长城汽车", ("601633_2024",)),
            ),
        ),
    )

    async with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "比亚迪和长城汽车的供应链风险有哪些差异"},
    ) as response:
        body = ""
        async for chunk in response.aiter_text():
            body += chunk

    events = _sse_body(body)
    assert '"answer_type"' not in events["delta"]
    assert "### 比亚迪" in json.loads(events["delta"])["text"]
    done = json.loads(events["done"])
    assert done["route"] == "rag_compare"
    assert done["comparison"]["comparison_allowed"] is True


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
    assert done["total_latency_ms"] > 0


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
    from app.models.llm import ChatResult
    from app.chat.schemas import Citation

    class InventLLM:
        model_id = "deepseek-flash"

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
