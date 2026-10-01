import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.obs.performance import (
    clear_performance_traces,
    list_performance_traces,
    performance_overview,
    record_performance,
)


@pytest.fixture(autouse=True)
def _reset_performance_traces():
    clear_performance_traces()
    yield
    clear_performance_traces()


def test_performance_trace_keeps_stage_timings_without_business_content():
    row = record_performance(
        {
            "status": "ok",
            "route": "rag",
            "model": "deepseek-flash",
            "timing_ms": {
                "routing": 120.0,
                "answer_model": 800.0,
                "validation": 2.0,
                "total": 930.0,
            },
            "rag": {
                "timing_ms": {"embed": 20.0, "vector_search": 10.0, "rerank": 80.0},
                "rerank_backend": "bge",
            },
        }
    )

    assert "question" not in row
    assert row["timing_ms"]["total"] == 930.0
    assert row["rag"]["timing_ms"]["rerank"] == 80.0
    assert list_performance_traces()["items"][0]["route"] == "rag"
    summary = performance_overview()
    assert summary["p50_total_ms"] == 930.0
    assert summary["avg_stage_ms"]["answer_model"] == 800.0


@pytest.mark.anyio
async def test_performance_trace_endpoints():
    record_performance(
        {
            "status": "ok",
            "route": "metric",
            "timing_ms": {"asknum": 12.0, "total": 15.0},
        }
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        traces = await client.get("/ops/performance-traces")
        overview = await client.get("/ops/performance/overview")

    assert traces.status_code == 200
    assert traces.json()["items"][0]["timing_ms"]["asknum"] == 12.0
    assert traces.json()["summary"]["count"] == 1
    assert overview.status_code == 200
    assert overview.json()["by_route"]["metric"] == 1
