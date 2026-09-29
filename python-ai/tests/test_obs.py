import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.obs.generations import clear_generations, record_from_chat, record_generation
from app.chat.schemas import ChatResponse


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_obs():
    clear_generations()
    yield
    clear_generations()


def test_record_masks_secrets_and_keeps_prompt_version():
    row = record_generation(
        {
            "route": "general",
            "model": "deepseek",
            "prompt_name": "chat.general",
            "prompt_version": "1.0.0",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "latency_ms": 200,
            "cost_usd": 0.0001,
            "input": "DEEPSEEK_API_KEY=sk-abcdefghijklmnopqrstuvwxyz 电话 13812345678",
            "output": "ok",
        }
    )
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in row["input"]
    assert "13812345678" not in row["input"]
    assert row["prompt_version"] == "1.0.0"


def test_record_from_chat_binds_pinned_prompt():
    response = ChatResponse(
        reply="审慎监管是对金融机构持续稳健经营的要求。",
        model="deepseek",
        route="general",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        latency_ms=100,
    )
    row = record_from_chat(response, message="什么是审慎监管")
    assert row["prompt_name"] == "chat.general"
    assert row["prompt_version"] == "1.0.0"
    assert row["cost_usd"] >= 0


@pytest.mark.anyio
async def test_obs_overview_and_traces_api():
    record_generation(
        {
            "route": "general",
            "model": "deepseek",
            "prompt_name": "chat.general",
            "prompt_version": "1.0.0",
            "prompt_tokens": 10,
            "completion_tokens": 10,
            "total_tokens": 20,
            "latency_ms": 80,
            "input": "hi",
            "output": "hello",
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        overview = await client.get("/ops/obs/overview")
        traces = await client.get("/ops/obs/traces")
    assert overview.status_code == 200
    body = overview.json()
    assert body["count"] >= 1
    assert body["store"] == "memory"
    assert traces.status_code == 200
    assert traces.json()["items"]
    assert traces.json()["summary"]["count"] >= 1
