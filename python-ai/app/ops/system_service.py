"""系统健康只检查依赖连通性；业务明细由各自的监控接口提供。"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from kombu import Connection
from redis import Redis

from app.config import get_settings
from app.db.connection import get_connection

logger = logging.getLogger(__name__)


def _probe_redis(url: str) -> dict[str, Any]:
    client = None
    try:
        started = time.perf_counter()
        client = Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=1.5)
        client.ping()
        result: dict[str, Any] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "used_memory_bytes": None,
            "connected_clients": None,
        }
        try:
            result["used_memory_bytes"] = int(client.info("memory")["used_memory"])
            result["connected_clients"] = int(client.info("clients")["connected_clients"])
        except Exception as exc:
            logger.warning("redis pressure metrics unavailable: %s", type(exc).__name__)
        return result
    except Exception as exc:
        logger.warning("redis dependency check failed: %s", type(exc).__name__)
        return {"status": "down", "latency_ms": None, "used_memory_bytes": None, "connected_clients": None}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                logger.warning("redis health-check client close failed: %s", type(exc).__name__)


def _probe_rabbitmq(url: str) -> dict[str, Any]:
    try:
        started = time.perf_counter()
        with Connection(url, connect_timeout=1.5) as connection:
            connection.connect()
            result: dict[str, Any] = {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "queue_status": "unavailable",
                "ready_messages": None,
                "consumer_count": None,
            }
            try:
                channel = connection.channel()
                _queue_name, message_count, consumer_count = channel.queue_declare(
                    queue="ingest", passive=True
                )
                result["queue_status"] = "ok"
                result["ready_messages"] = int(message_count)
                result["consumer_count"] = int(consumer_count)
            except Exception as exc:
                logger.warning("rabbitmq ingest queue metrics unavailable: %s", type(exc).__name__)
            return result
    except Exception as exc:
        logger.warning("rabbitmq dependency check failed: %s", type(exc).__name__)
        return {
            "status": "down", "latency_ms": None, "queue_status": "unavailable",
            "ready_messages": None, "consumer_count": None,
        }


def fetch_system_overview() -> dict[str, Any]:
    settings = get_settings()
    services: dict[str, dict[str, Any]] = {
        "python_ai": {"status": "ok", "service": "regops-python-ai"},
        "postgresql": {"status": "unknown", "latency_ms": None},
        "pgvector": {"status": "unknown", "installed": False},
        "redis": _probe_redis(settings.ingest_result_backend),
        "rabbitmq": _probe_rabbitmq(settings.ingest_broker_url),
    }
    try:
        started = time.perf_counter()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                services["postgresql"] = {
                    "status": "ok",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                cur.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                row = cur.fetchone()
                installed = bool(row[0]) if row else False
                services["pgvector"] = {
                    "status": "ok" if installed else "missing",
                    "installed": installed,
                }
    except Exception as exc:
        logger.warning("system dependency check failed: %s", type(exc).__name__)
        services["postgresql"] = {"status": "down", "latency_ms": None}
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "services": services}
