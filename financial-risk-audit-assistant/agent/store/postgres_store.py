from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .sqlite_store import LocalSqliteStore


class _PostgresConnection:
    """让现有 Store 查询复用 PostgreSQL；事务仍由业务方法统一 commit。"""

    def __init__(self, dsn: str):
        self._connection = psycopg.connect(dsn, row_factory=dict_row)
        self._dirty = False
        try:
            self._connection.execute("CREATE SCHEMA IF NOT EXISTS agent")
            self._connection.execute("SET search_path TO agent, public")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            self._connection.close()
            raise

    def execute(self, query: str, params: tuple[Any, ...] = ()):
        try:
            is_read = query.lstrip().upper().startswith("SELECT")
            cursor = self._connection.execute(query.replace("?", "%s"), params)
            if is_read and not self._dirty:
                # PostgreSQL 普通 SELECT 也开启事务；及时结束，避免 LangGraph
                # setup() 的 CREATE INDEX CONCURRENTLY 被长时间读事务阻塞。
                self._connection.commit()
            elif not is_read:
                self._dirty = True
            return cursor
        except Exception:
            self._connection.rollback()
            self._dirty = False
            raise

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()
        self._dirty = False

    def close(self) -> None:
        self._connection.close()


class PostgresBusinessStore(LocalSqliteStore):
    """Agent 业务 Store，使用独立的 agent schema，避免与 RegOps 表名冲突。"""

    def __init__(self, dsn: str):
        self._lock = threading.RLock()
        self._conn = _PostgresConnection(dsn)
        self._init_schema()

    def _init_schema(self) -> None:
        script = Path(__file__).with_name("postgres_schema.sql").read_text(encoding="utf-8")
        with self._lock:
            self._conn.executescript(script)
            self._ensure_column("threads", "user_prompt", "TEXT")
            self._ensure_column("threads", "sandbox_id", "TEXT")
            self._ensure_column("threads", "sandbox_project", "TEXT")
            self._ensure_column("runs", "user_question", "TEXT")
            self._conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        # 表名和字段名仅由本模块硬编码调用，不接受用户输入。
        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")

    @staticmethod
    def _duration_ms_sql() -> str:
        return "EXTRACT(EPOCH FROM (r.finished_at::timestamptz - r.started_at::timestamptz)) * 1000"
