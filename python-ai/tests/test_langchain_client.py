import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from app.config import Settings
from app.models.llm import ModelTimeoutError, get_llm_client, list_available_models, resolve_model_id
from app.models import llm as llm_module


@pytest.fixture(autouse=True)
def clear_llm_client_cache():
    llm_module._client_for_config.cache_clear()
    yield
    llm_module._client_for_config.cache_clear()


class FakeChatModel:
    def __init__(self, response: AIMessage | None = None, chunks: list[AIMessageChunk] | None = None):
        self.response = response
        self.chunks = chunks or []
        self.messages = []
        self.temperature = None

    async def ainvoke(self, messages, *, temperature):
        self.messages = messages
        self.temperature = temperature
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def invoke(self, messages, *, temperature):
        self.messages = messages
        self.temperature = temperature
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def astream(self, messages, *, temperature):
        self.messages = messages
        self.temperature = temperature
        for chunk in self.chunks:
            yield chunk


def _settings() -> Settings:
    return Settings(
        deepseek_api_key="test-deepseek-key",
        qwen_api_key="test-qwen-key",
        default_model="deepseek",
        deepseek_model_ids="deepseek-flash,deepseek-v4-pro",
        qwen_model_ids="qwen3.8-max,qwen3.8-flash,qwen3.7-plus",
    )


def test_factory_lists_concrete_models_and_accepts_provider_aliases(monkeypatch):
    created = []
    monkeypatch.setattr(
        "app.models.llm.init_chat_model",
        lambda **kwargs: created.append(kwargs) or FakeChatModel(),
    )
    settings = _settings()

    available = list_available_models(settings)
    assert available == [
        "deepseek-flash",
        "deepseek-v4-pro",
        "qwen3.8-max",
        "qwen3.8-flash",
        "qwen3.7-plus",
    ]
    assert resolve_model_id("deepseek", available) == "deepseek-flash"
    assert resolve_model_id("qwen", available) == "qwen3.8-max"
    get_llm_client(settings, model="deepseek-v4-pro")
    get_llm_client(settings, model="qwen")

    assert [item["model"] for item in created] == ["deepseek-v4-pro", "qwen3.8-max"]
    assert created[0]["model_provider"] == "openai"
    assert created[0]["stream_usage"] is True
    assert created[0]["max_tokens"] == settings.llm_max_output_tokens
    assert created[1]["base_url"] == settings.qwen_base_url


@pytest.mark.asyncio
async def test_langchain_client_converts_messages_and_usage(monkeypatch):
    fake = FakeChatModel(
        AIMessage(
            content="已查到",
            usage_metadata={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
        )
    )
    monkeypatch.setattr("app.models.llm.init_chat_model", lambda **_kwargs: fake)
    client = get_llm_client(_settings())

    result = await client.chat_with_usage(
        [{"role": "system", "content": "谨慎回答"}, {"role": "user", "content": "查营收"}],
        temperature=0.3,
    )

    assert isinstance(fake.messages[0], SystemMessage)
    assert isinstance(fake.messages[1], HumanMessage)
    assert fake.temperature == 0.3
    assert result.content == "已查到"
    assert result.total_tokens == 20
    assert result.latency_ms >= 0


def test_langchain_client_supports_sync_rag_call(monkeypatch):
    fake = FakeChatModel(
        AIMessage(
            content='{"supports_answer":false,"ranked":[]}',
            usage_metadata={"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
        )
    )
    monkeypatch.setattr("app.models.llm.init_chat_model", lambda **_kwargs: fake)
    client = get_llm_client(_settings())

    result = client.chat_with_usage_sync(
        [{"role": "system", "content": "重排"}, {"role": "user", "content": "候选"}],
        temperature=0.0,
    )

    assert isinstance(fake.messages[0], SystemMessage)
    assert isinstance(fake.messages[1], HumanMessage)
    assert fake.temperature == 0.0
    assert result.total_tokens == 38



@pytest.mark.asyncio
async def test_langchain_client_streams_text_and_reports_usage(monkeypatch):
    fake = FakeChatModel(
        chunks=[
            AIMessageChunk(content="你"),
            AIMessageChunk(content="好"),
            AIMessageChunk(content="", usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}),
        ]
    )
    monkeypatch.setattr("app.models.llm.init_chat_model", lambda **_kwargs: fake)
    client = get_llm_client(_settings())

    deltas = [item async for item in client.chat_stream([{"role": "user", "content": "你好"}])]

    assert [item.text for item in deltas if item.text] == ["你", "好"]
    assert deltas[-1].done is True
    assert deltas[-1].result.content == "你好"
    assert deltas[-1].result.prompt_tokens == 5
    assert deltas[-1].result.completion_tokens == 2
    assert deltas[-1].result.latency_ms >= 0


@pytest.mark.asyncio
async def test_langchain_client_maps_timeout_to_existing_error(monkeypatch):
    fake = FakeChatModel(response=httpx.ReadTimeout("timed out"))
    monkeypatch.setattr("app.models.llm.init_chat_model", lambda **_kwargs: fake)
    client = get_llm_client(_settings())

    with pytest.raises(ModelTimeoutError):
        await client.chat_with_usage([{"role": "user", "content": "你好"}])
