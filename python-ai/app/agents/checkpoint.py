"""w6-2：LangGraph Checkpoint。保存图执行快照，不是对话 Memory。"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.budget import current_limits
from app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_DEPT = "public"
_DEPT_RE = re.compile(r"^[a-z0-9_]{2,32}$")
_THREAD_RE = re.compile(r"^([a-z0-9_]{2,32}):([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")

_lock = threading.Lock()
_process_saver: SqliteSaver | None = None
_process_conn: sqlite3.Connection | None = None


def normalize_dept(dept: str | None) -> str:
    value = (dept or DEFAULT_DEPT).strip().lower()
    if not _DEPT_RE.match(value):
        return DEFAULT_DEPT
    return value


def make_thread_id(dept: str | None = None) -> str:
    return f"{normalize_dept(dept)}:{uuid4()}"


def parse_thread_dept(thread_id: str | None) -> str | None:
    if not thread_id:
        return None
    match = _THREAD_RE.match(thread_id.strip())
    return match.group(1) if match else None


def thread_belongs_to_dept(thread_id: str | None, dept: str | None) -> bool:
    expected = parse_thread_dept(thread_id)
    return expected is not None and expected == normalize_dept(dept)


def graph_config(thread_id: str) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": max(4, int(current_limits().max_steps)),
    }


def open_sqlite_checkpointer(path: str | Path) -> SqliteSaver:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(file_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def get_process_checkpointer() -> SqliteSaver:
    global _process_saver, _process_conn
    with _lock:
        if _process_saver is None:
            path = get_settings().checkpoint_sqlite_path
            _process_saver = open_sqlite_checkpointer(path)
            _process_conn = _process_saver.conn
            logger.info("review checkpoint sqlite=%s", path)
        return _process_saver


def reset_process_checkpointer() -> None:
    global _process_saver, _process_conn
    with _lock:
        if _process_conn is not None:
            _process_conn.close()
        _process_saver = None
        _process_conn = None


def checkpoint_expired(created_at: datetime | str | None, *, ttl_hours: float | None = None) -> bool:
    if created_at is None:
        return False
    if isinstance(created_at, str):
        text = created_at.replace("Z", "+00:00")
        try:
            created_at = datetime.fromisoformat(text)
        except ValueError:
            return False
    hours = get_settings().checkpoint_ttl_hours if ttl_hours is None else ttl_hours
    if hours <= 0:
        return False
    when = created_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return now - when.astimezone(timezone.utc) > timedelta(hours=hours)
