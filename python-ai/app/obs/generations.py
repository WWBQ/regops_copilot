"""本地 LLM generation 环形缓冲 + 可选 Langfuse。"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.prompts.library import PromptLibraryError, active_version
from app.request_id import current_request_id, current_trace_id, current_traceparent
from app.chat.schemas import ChatResponse
from app.obs.privacy import mask_for_log

logger = logging.getLogger(__name__)

_MAX = 200
_lock = threading.Lock()
_items: deque[dict[str, Any]] = deque(maxlen=_MAX)

# Approximate public list prices (USD / 1M tokens). Not invoices.
_RATES_USD_PER_1M: dict[str, tuple[float, float]] = {
    "deepseek": (0.14, 0.28),
    "qwen": (0.30, 0.90),
}
_DEFAULT_RATE = (0.50, 1.50)

_ROUTE_PROMPT = {
    "general": "chat.general",
    "chitchat": "chat.general",
    "rag": "rag.answer",
    "rag_blocked": "rag.answer",
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    key = (model or "").lower()
    rates = _DEFAULT_RATE
    for name, pair in _RATES_USD_PER_1M.items():
        if name in key:
            rates = pair
            break
    return round((prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1_000_000, 8)


def prompt_for_route(route: str) -> tuple[str | None, str | None]:
    name = _ROUTE_PROMPT.get(route)
    if not name:
        return None, None
    try:
        return name, active_version(name)
    except PromptLibraryError:
        return name, None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 2)


def record_generation(payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload)
    row.setdefault("id", str(uuid4()))
    row.setdefault("created_at", _now())
    row.setdefault("request_id", current_request_id())
    row.setdefault("trace_id", current_trace_id())
    row.setdefault("traceparent", current_traceparent())
    if row.get("input"):
        row["input"] = mask_for_log(str(row["input"]))[:800]
    if row.get("output"):
        row["output"] = mask_for_log(str(row["output"]))[:800]
    with _lock:
        _items.appendleft(row)
    try:
        from app.obs.langfuse_client import maybe_export

        maybe_export(row)
    except Exception:
        logger.debug("langfuse export skipped", exc_info=True)
    return row


def record_from_chat(
    response: ChatResponse,
    *,
    message: str,
    stream: bool = False,
    ttft_ms: float | None = None,
) -> dict[str, Any]:
    prompt_name, prompt_version = prompt_for_route(response.route)
    prompt_tokens = int(response.prompt_tokens or 0)
    completion_tokens = int(response.completion_tokens or 0)
    latency_ms = float(response.latency_ms or 0)
    tokens_per_s = None
    if completion_tokens and latency_ms > 0:
        tokens_per_s = round(completion_tokens / (latency_ms / 1000.0), 2)
    return record_generation(
        {
            "route": response.route,
            "model": response.model,
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(response.total_tokens or (prompt_tokens + completion_tokens)),
            "latency_ms": latency_ms,
            "ttft_ms": ttft_ms,
            "tokens_per_s": tokens_per_s,
            "cost_usd": estimate_cost_usd(response.model, prompt_tokens, completion_tokens),
            "stream": stream,
            "session_id": response.session_id,
            "input": message,
            "output": response.reply,
        }
    )


def list_generations(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    with _lock:
        rows = list(_items)
    total = len(rows)
    sliced = rows[offset : offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "items": sliced}


def overview() -> dict[str, Any]:
    from app.config import get_settings

    with _lock:
        rows = list(_items)
    latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms")]
    ttfts = [float(row["ttft_ms"]) for row in rows if row.get("ttft_ms") is not None]
    tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
    cost = sum(float(row.get("cost_usd") or 0) for row in rows)
    speeds = [float(row["tokens_per_s"]) for row in rows if row.get("tokens_per_s")]
    with_prompt = sum(1 for row in rows if row.get("prompt_version"))
    settings = get_settings()
    langfuse_on = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    return {
        "count": len(rows),
        "p95_latency_ms": _percentile(latencies, 95),
        "p50_latency_ms": _percentile(latencies, 50),
        "ttft_p95_ms": _percentile(ttfts, 95),
        "avg_tokens_per_s": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "tokens_sum": tokens,
        "cost_usd_sum": round(cost, 6),
        "prompt_version_rate": round(with_prompt / len(rows), 4) if rows else 0,
        "langfuse_enabled": langfuse_on,
        "langfuse_host": settings.langfuse_host if langfuse_on else None,
        "store": "memory",
        "note": "成本按公开标价估算，不是账单。未配 Langfuse Key 时只写本地环形缓冲。",
    }


def clear_generations() -> None:
    with _lock:
        _items.clear()
