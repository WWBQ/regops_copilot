"""Optional Langfuse ingestion. Missing keys → no-op. Never blocks chat."""

from __future__ import annotations

import base64
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


def maybe_export(row: dict[str, Any]) -> None:
    from app.config import get_settings

    settings = get_settings()
    public = (settings.langfuse_public_key or "").strip()
    secret = (settings.langfuse_secret_key or "").strip()
    if not public or not secret:
        return
    host = (settings.langfuse_host or "https://cloud.langfuse.com").rstrip("/")
    thread = threading.Thread(
        target=_post,
        args=(host, public, secret, row),
        daemon=True,
        name="langfuse-export",
    )
    thread.start()


def _post(host: str, public: str, secret: str, row: dict[str, Any]) -> None:
    token = base64.b64encode(f"{public}:{secret}".encode()).decode("ascii")
    now = datetime.now(timezone.utc).isoformat()
    trace_id = str(row.get("trace_id") or uuid4().hex)
    generation_id = str(row.get("id") or uuid4())
    body = {
        "batch": [
            {
                "id": str(uuid4()),
                "type": "trace-create",
                "timestamp": now,
                "body": {
                    "id": trace_id,
                    "name": row.get("route") or "chat",
                    "input": row.get("input"),
                    "output": row.get("output"),
                    "metadata": {
                        "request_id": row.get("request_id"),
                        "prompt_name": row.get("prompt_name"),
                        "prompt_version": row.get("prompt_version"),
                    },
                },
            },
            {
                "id": str(uuid4()),
                "type": "generation-create",
                "timestamp": now,
                "body": {
                    "id": generation_id,
                    "traceId": trace_id,
                    "name": row.get("prompt_name") or "llm",
                    "model": row.get("model"),
                    "input": row.get("input"),
                    "output": row.get("output"),
                    "usage": {
                        "input": row.get("prompt_tokens") or 0,
                        "output": row.get("completion_tokens") or 0,
                        "total": row.get("total_tokens") or 0,
                    },
                    "metadata": {
                        "prompt_version": row.get("prompt_version"),
                        "cost_usd": row.get("cost_usd"),
                        "route": row.get("route"),
                    },
                },
            },
        ]
    }
    try:
        httpx.post(
            f"{host}/api/public/ingestion",
            content=json.dumps(body),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            },
            timeout=2.0,
        )
    except Exception:
        logger.debug("langfuse ingest failed", exc_info=True)
