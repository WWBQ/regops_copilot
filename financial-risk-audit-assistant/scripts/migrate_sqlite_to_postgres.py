"""一次性把旧 Agent SQLite 数据导入 PostgreSQL；可重复运行且不覆盖新数据。"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg import sql

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

from agent.core.persistence import make_postgres_checkpointer, make_postgres_langgraph_store
from agent.core.settings import (
    AGENT_DATABASE_URL, CHECKPOINT_DB_PATH, LANGGRAPH_STORE_DB_PATH, STORE_DB_PATH,
)
from agent.store.postgres_store import PostgresBusinessStore


BUSINESS_TABLES = (
    "threads", "runs", "run_events", "agent_trace_events", "thread_messages",
    "thread_plans", "review_findings", "risk_audit_results", "risk_audit_findings", "settings",
)


def sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_business() -> None:
    if not STORE_DB_PATH.exists():
        return
    target = PostgresBusinessStore(AGENT_DATABASE_URL)
    target.close()
    source = sqlite_readonly(STORE_DB_PATH)
    try:
        with psycopg.connect(AGENT_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SET search_path TO agent, public")
                for table in BUSINESS_TABLES:
                    rows = source.execute(f"SELECT * FROM {table}").fetchall()
                    if not rows:
                        continue
                    columns = tuple(rows[0].keys())
                    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                        sql.Identifier(table),
                        sql.SQL(", ").join(map(sql.Identifier, columns)),
                        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                    )
                    cur.executemany(query, (tuple(row) for row in rows))
                    print(f"business {table}: {len(rows)} source rows")
    finally:
        source.close()


def migrate_checkpoints() -> None:
    if not CHECKPOINT_DB_PATH.exists():
        return
    source_conn = sqlite_readonly(CHECKPOINT_DB_PATH)
    target, target_conn = make_postgres_checkpointer(AGENT_DATABASE_URL)
    try:
        source = SqliteSaver(source_conn)
        existing = {
            (item.config["configurable"]["thread_id"],
             item.config["configurable"].get("checkpoint_ns", ""),
             item.config["configurable"]["checkpoint_id"])
            for item in target.list(None)
        }
        items = list(source.list(None))
        items.sort(key=lambda item: (
            item.config["configurable"]["thread_id"],
            item.config["configurable"].get("checkpoint_ns", ""),
            item.config["configurable"]["checkpoint_id"],
        ))
        copied = 0
        for item in items:
            config = item.config["configurable"]
            key = (config["thread_id"], config.get("checkpoint_ns", ""), config["checkpoint_id"])
            if key in existing:
                continue
            parent = item.parent_config or {
                "configurable": {"thread_id": config["thread_id"], "checkpoint_ns": config.get("checkpoint_ns", "")}
            }
            versions = item.checkpoint.get("channel_versions", {})
            target.put(parent, item.checkpoint, item.metadata, versions)
            by_task: dict[str, list[tuple[str, object]]] = defaultdict(list)
            for task_id, channel, value in item.pending_writes:
                by_task[task_id].append((channel, value))
            for task_id, writes in by_task.items():
                target.put_writes(item.config, writes, task_id)
            copied += 1
        print(f"checkpoints: {copied} imported / {len(items)} source")
        for thread_id in {item.config["configurable"]["thread_id"] for item in items}:
            config = {"configurable": {"thread_id": thread_id}}
            old = source.get_tuple(config)
            new = target.get_tuple(config)
            if old is None or new is None or old.checkpoint["id"] != new.checkpoint["id"]:
                raise RuntimeError(f"checkpoint latest mismatch: {thread_id}")
    finally:
        target_conn.close()
        source_conn.close()


def migrate_memories() -> None:
    if not LANGGRAPH_STORE_DB_PATH.exists():
        return
    source_conn = sqlite_readonly(LANGGRAPH_STORE_DB_PATH)
    target, target_conn = make_postgres_langgraph_store(AGENT_DATABASE_URL)
    try:
        source = SqliteStore(source_conn)
        namespaces = source.list_namespaces(limit=10000)
        copied = 0
        for namespace in namespaces:
            offset = 0
            while True:
                items = source.search(namespace, limit=100, offset=offset)
                if not items:
                    break
                for item in items:
                    if target.get(namespace, item.key) is None:
                        target.put(namespace, item.key, item.value)
                        copied += 1
                offset += len(items)
        print(f"memories: {copied} imported")
    finally:
        target_conn.close()
        source_conn.close()


if __name__ == "__main__":
    migrate_business()
    migrate_checkpoints()
    migrate_memories()
