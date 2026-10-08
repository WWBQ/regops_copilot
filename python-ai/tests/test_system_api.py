"""系统概览 API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from contextlib import contextmanager
from unittest.mock import MagicMock

from app.main import app
from app.ops import system_service


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_system_overview(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(system_service, "_probe_redis", lambda _url: {"status": "ok", "used_memory_bytes": 1024})
    monkeypatch.setattr(system_service, "_probe_rabbitmq", lambda _url: {"status": "ok", "ready_messages": 2})
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.side_effect = [(1,), (True,)]

    @contextmanager
    def fake_connection():
        yield conn

    monkeypatch.setattr(system_service, "get_connection", fake_connection)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ops/system/overview")
    assert response.status_code == 200
    body = response.json()
    assert "services" in body
    assert body["services"]["python_ai"]["status"] == "ok"
    assert body["services"]["postgresql"]["status"] == "ok"
    assert body["services"]["pgvector"]["installed"] is True
    assert body["services"]["redis"]["used_memory_bytes"] == 1024
    assert body["services"]["rabbitmq"]["ready_messages"] == 2
    assert "corpus" not in body
    assert "rag_traces" not in body
    assert "ingest_jobs" not in body


def test_redis_probe_reads_pressure_without_writing(monkeypatch: pytest.MonkeyPatch):
    client = MagicMock()
    client.info.side_effect = [{"used_memory": 4096}, {"connected_clients": 3}]
    monkeypatch.setattr(system_service.Redis, "from_url", lambda *_args, **_kwargs: client)

    result = system_service._probe_redis("redis://localhost:6379/1")

    assert result["status"] == "ok"
    assert result["used_memory_bytes"] == 4096
    assert result["connected_clients"] == 3
    client.ping.assert_called_once()
    client.close.assert_called_once()


def test_rabbitmq_probe_uses_passive_queue_declare(monkeypatch: pytest.MonkeyPatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.channel.return_value.queue_declare.return_value = ("ingest", 7, 2)
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(system_service, "Connection", factory)

    result = system_service._probe_rabbitmq("amqp://broker//")

    assert result["status"] == "ok"
    assert result["ready_messages"] == 7
    assert result["consumer_count"] == 2
    connection.channel.return_value.queue_declare.assert_called_once_with(queue="ingest", passive=True)
    factory.assert_called_once_with("amqp://broker//", connect_timeout=1.5)


def test_broker_down_is_not_reported_as_zero_queue(monkeypatch: pytest.MonkeyPatch):
    factory = MagicMock(side_effect=ConnectionError("down"))
    monkeypatch.setattr(system_service, "Connection", factory)

    result = system_service._probe_rabbitmq("amqp://broker//")

    assert result["status"] == "down"
    assert result["ready_messages"] is None
