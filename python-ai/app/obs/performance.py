"""统一请求性能 Trace：只记录阶段耗时和路由元数据，不记录业务正文。"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.request_id import current_request_id, current_trace_id, current_traceparent

logger = logging.getLogger(__name__)

_MAX = 500
_lock = threading.Lock()
_items: deque[dict[str, Any]] = deque(maxlen=_MAX)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 2)


def record_performance(payload: dict[str, Any]) -> dict[str, Any]:
    """写入内存环形缓冲和标准日志；payload 只能包含脱敏后的性能元数据。"""
    row = dict(payload)
    row.setdefault("id", str(uuid4()))
    row.setdefault("created_at", _now())
    row.setdefault("request_id", current_request_id())
    row.setdefault("trace_id", current_trace_id())
    row.setdefault("traceparent", current_traceparent())
    with _lock:
        _items.appendleft(row)
    logger.info("performance_trace %s", json.dumps(row, ensure_ascii=False, default=str))
    return row


def list_performance_traces(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    with _lock:
        rows = list(_items)
    return {
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "items": rows[offset : offset + limit],
    }


def performance_overview() -> dict[str, Any]:
    with _lock:
        rows = list(_items)
    totals: list[float] = []
    stage_values: dict[str, list[float]] = defaultdict(list)
    by_route: dict[str, int] = defaultdict(int)
    errors = 0
    for row in rows:
        timing = row.get("timing_ms") or {}
        total = timing.get("total")
        if isinstance(total, (int, float)):
            totals.append(float(total))
        for name, value in timing.items():
            if name == "total" or not isinstance(value, (int, float)):
                continue
            stage_values[name].append(float(value))
        by_route[str(row.get("route") or "unknown")] += 1
        if row.get("status") != "ok":
            errors += 1
    return {
        "count": len(rows),
        "p50_total_ms": _percentile(totals, 50),
        "p95_total_ms": _percentile(totals, 95),
        "error_count": errors,
        "by_route": dict(by_route),
        "avg_stage_ms": {
            name: round(sum(values) / len(values), 2)
            for name, values in sorted(stage_values.items())
            if values
        },
        "store": "memory+application_log",
    }


def clear_performance_traces() -> None:
    with _lock:
        _items.clear()
