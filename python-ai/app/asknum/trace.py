"""问数 trace：写入 asknum_query_log，失败不阻断答数。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.db.asknum_trace_repository import insert_asknum_trace
from app.db.connection import get_connection

logger = logging.getLogger(__name__)


@dataclass
class AsknumTrace:
    question: str
    route: str
    company_codes: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    year: int | None = None
    year_defaulted: bool = False
    scope: str | None = None
    narrative: bool = False
    lookups: list[dict[str, Any]] = field(default_factory=list)
    total_ms: float = 0.0
    request_id: str | None = None
    session_id: str | None = None


def save_asknum_trace(trace: AsknumTrace) -> int | None:
    try:
        with get_connection() as conn:
            row_id = insert_asknum_trace(conn, trace)
            conn.commit()
            return row_id
    except Exception:
        logger.exception("failed to persist asknum trace route=%s", trace.route)
        return None
