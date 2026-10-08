from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    """统一使用 UTC 时间存储，避免本地时区变化影响排序和排查。"""

    return datetime.now(UTC).isoformat()


class LocalSqliteStore:
    """业务数据 Store。

    这个类只负责保存“平台业务摘要”，不保存完整聊天历史：
    - threads：任务列表和当前状态。
    - runs：每次运行的开始、结束、失败原因。
    - thread_plans：编码前的技术方案、确认状态和 Markdown 归档路径。
    - review_findings：Reviewer Agent 发现的问题。
    - settings：项目的少量键值配置。

    完整 messages 和 LangGraph thread state 由 checkpoint 数据库保存。
    """

    def __init__(self, db_path: Path):
        # check_same_thread=False 允许 FastAPI 后台任务、SSE 读取和工具写事件跨线程访问。
        # 但 sqlite3 的同一个连接不能无锁并发提交，所以必须用 RLock 串行化所有数据库操作。
        self.db_path = db_path
        self._lock = threading.RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._init_schema()

    def _configure_connection(self) -> None:
        """配置 SQLite 连接，提升本地多线程读写稳定性。

        WAL 模式允许读写更好地并发；busy_timeout 可以让短时间锁等待自动重试，
        避免 Agent 正在写事件时前端 SSE 读取刚好撞上锁就失败。
        """

        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            # 事件记录有时会早于 thread 主记录写入；这里不启用外键强校验，
            # 由 delete_thread 主动清理附属记录即可，避免展示事件影响主任务。
            self._conn.execute("PRAGMA foreign_keys=OFF")

    def close(self) -> None:
        """关闭 SQLite 连接，主要供独立验证脚本释放临时数据库文件。"""

        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        """初始化业务表。

        CREATE TABLE IF NOT EXISTS 让服务可以重复启动；
        第一次启动会创建表，后续启动只复用已有 SQLite 文件。
        """

        with self._lock:
            self._conn.executescript(
                """
            CREATE TABLE IF NOT EXISTS threads (
              thread_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              user_prompt TEXT,
              repo_url TEXT,
              repo_owner TEXT,
              repo_name TEXT,
              branch_name TEXT,
              pr_url TEXT,
              latest_run_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              status TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              error TEXT,
              user_question TEXT,
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
            );

            CREATE TABLE IF NOT EXISTS run_events (
              id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              title TEXT NOT NULL,
              status TEXT NOT NULL,
              detail TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
            );

            CREATE TABLE IF NOT EXISTS agent_trace_events (
              id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              thread_id TEXT NOT NULL,
              phase TEXT NOT NULL,
              label TEXT NOT NULL,
              status TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_agent_trace_run_time
              ON agent_trace_events(run_id, started_at);

            CREATE TABLE IF NOT EXISTS thread_messages (
              message_id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              run_id TEXT,
              author TEXT NOT NULL,
              content TEXT NOT NULL,
              metadata TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
            );

            CREATE TABLE IF NOT EXISTS thread_plans (
              plan_id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              run_id TEXT,
              status TEXT NOT NULL,
              prompt TEXT NOT NULL,
              plan_text TEXT NOT NULL,
              plan_path TEXT NOT NULL,
              created_at TEXT NOT NULL,
              approved_at TEXT,
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
            );

            CREATE TABLE IF NOT EXISTS review_findings (
              id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              file TEXT NOT NULL,
              line INTEGER,
              severity TEXT NOT NULL,
              title TEXT NOT NULL,
              description TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
            );

            CREATE TABLE IF NOT EXISTS risk_audit_results (
              result_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL UNIQUE,
              thread_id TEXT NOT NULL,
              company_code TEXT NOT NULL,
              company_name TEXT NOT NULL,
              year INTEGER NOT NULL,
              status TEXT NOT NULL,
              summary TEXT NOT NULL,
              evidence_gaps TEXT NOT NULL,
              report_markdown TEXT NOT NULL,
              answer_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id),
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS risk_audit_findings (
              id TEXT PRIMARY KEY,
              result_id TEXT NOT NULL,
              thread_id TEXT NOT NULL,
              ordinal INTEGER NOT NULL,
              risk_type TEXT NOT NULL,
              severity TEXT NOT NULL,
              conclusion TEXT NOT NULL,
              evidence_ids TEXT NOT NULL,
              data_points TEXT NOT NULL,
              uncertainty TEXT NOT NULL,
              review_question TEXT NOT NULL,
              review_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(result_id) REFERENCES risk_audit_results(result_id),
              FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
            );

            CREATE INDEX IF NOT EXISTS idx_risk_results_thread_created
              ON risk_audit_results(thread_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_risk_findings_result_ordinal
              ON risk_audit_findings(result_id, ordinal);

            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            """
            )
            self._ensure_column("threads", "user_prompt", "TEXT")
            self._ensure_column("runs", "user_question", "TEXT")
            self._conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """为旧 SQLite 数据库补充新增列。

        项目会不断迭代字段，不能要求每次都删除 data/store.sqlite。
        PRAGMA table_info 可以判断列是否存在，缺失时用 ALTER TABLE 做轻量迁移。
        """

        with self._lock:
            rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            existing_columns = {row["name"] for row in rows}
            if column not in existing_columns:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def upsert_thread(
        self,
        *,
        thread_id: str,
        title: str,
        repo_url: str | None = None,
        repo_owner: str | None = None,
        repo_name: str | None = None,
        branch_name: str | None = None,
        pr_url: str | None = None,
        user_prompt: str | None = None,
        latest_run_status: str = "pending",
    ) -> None:
        with self._lock:
            now = utc_now()
            existing = self.get_thread(thread_id)
            created_at = existing["created_at"] if existing else now
            self._conn.execute(
                """
                INSERT INTO threads (
                  thread_id, title, user_prompt, repo_url, repo_owner, repo_name, branch_name, pr_url,
                  latest_run_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                  title=threads.title,
                  user_prompt=COALESCE(excluded.user_prompt, threads.user_prompt),
                  repo_url=COALESCE(excluded.repo_url, threads.repo_url),
                  repo_owner=COALESCE(excluded.repo_owner, threads.repo_owner),
                  repo_name=COALESCE(excluded.repo_name, threads.repo_name),
                  branch_name=COALESCE(excluded.branch_name, threads.branch_name),
                  pr_url=COALESCE(excluded.pr_url, threads.pr_url),
                  latest_run_status=excluded.latest_run_status,
                  updated_at=excluded.updated_at
                """,
                (
                    thread_id,
                    title,
                    user_prompt,
                    repo_url,
                    repo_owner,
                    repo_name,
                    branch_name,
                    pr_url,
                    latest_run_status,
                    created_at,
                    now,
                ),
            )
            self._conn.commit()

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM threads WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            return self._row_to_dict(row)

    def list_threads(self, limit: int = 50, *, owner_prefix: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if owner_prefix is None:
                rows = self._conn.execute(
                    "SELECT * FROM threads ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM threads WHERE substr(thread_id, 1, ?) = ? ORDER BY updated_at DESC LIMIT ?",
                    (len(owner_prefix), owner_prefix, limit),
                ).fetchall()
            return [dict(row) for row in rows]

    def update_thread_status(
        self,
        thread_id: str,
        status: str,
        *,
        pr_url: str | None = None,
        branch_name: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE threads
                SET latest_run_status = ?,
                    pr_url = COALESCE(?, pr_url),
                    branch_name = COALESCE(?, branch_name),
                    updated_at = ?
                WHERE thread_id = ?
                """,
                (status, pr_url, branch_name, utc_now(), thread_id),
            )
            self._conn.commit()

    def record_run(
        self,
        *,
        run_id: str,
        thread_id: str,
        status: str,
        error: str | None = None,
        finished: bool = False,
        user_question: str | None = None,
    ) -> None:
        with self._lock:
            now = utc_now()
            question = user_question.strip()[:2000] if user_question and user_question.strip() else None
            self._conn.execute(
                """
                INSERT INTO runs (run_id, thread_id, status, started_at, finished_at, error, user_question)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  status=excluded.status,
                  finished_at=excluded.finished_at,
                  error=excluded.error,
                  user_question=COALESCE(excluded.user_question, runs.user_question)
                """,
                (run_id, thread_id, status, now, now if finished else None, error, question),
            )
            self._conn.commit()

    def add_run_event(
        self,
        *,
        event_id: str,
        thread_id: str,
        kind: str,
        title: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        """记录 Agent 运行过程中的简洁步骤。

        这些事件用于 Dashboard 实时展示“正在做什么”，不保存大段命令输出。
        相同 event_id 可以被更新，例如先写 in_progress，完成后改成 completed。
        """

        with self._lock:
            now = utc_now()
            self._conn.execute(
                """
                INSERT INTO run_events (
                  id, thread_id, kind, title, status, detail, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  kind=excluded.kind,
                  title=excluded.title,
                  status=excluded.status,
                  detail=excluded.detail,
                  updated_at=excluded.updated_at
                """,
                (event_id, thread_id, kind, title, status, detail, now, now),
            )
            self._conn.commit()

    def list_run_events(self, thread_id: str) -> list[dict[str, Any]]:
        """按创建顺序读取运行步骤。"""

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM run_events
                WHERE thread_id = ?
                ORDER BY created_at ASC
                """,
                (thread_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_agent_trace_event(
        self, *, event_id: str, run_id: str, thread_id: str,
        phase: str, label: str, status: str,
    ) -> None:
        """持久化 run 级别轨迹；只存简短标签，不存原始工具参数或输出。"""

        if phase not in {"user", "model", "tool", "subagent"}:
            raise ValueError("invalid trace phase")
        if status not in {"running", "completed", "failed"}:
            raise ValueError("invalid trace status")
        with self._lock:
            now = utc_now()
            self._conn.execute(
                """
                INSERT INTO agent_trace_events
                  (id, run_id, thread_id, phase, label, status, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  status=excluded.status, finished_at=excluded.finished_at
                """,
                (event_id, run_id, thread_id, phase, label[:200], status, now,
                 now if status != "running" else None),
            )
            self._conn.commit()

    def get_agent_run_trace(self, *, run_id: str, owner_prefix: str) -> dict[str, Any] | None:
        """只允许会话所有者读取轨迹。旧 run 没有轨迹时返回空列表。"""

        with self._lock:
            row = self._conn.execute(
                """
                SELECT r.run_id, r.thread_id, r.status, r.started_at, r.finished_at, r.error,
                       t.title AS session_title,
                       COALESCE(NULLIF(TRIM(r.user_question), ''),
                         (SELECT e.label FROM agent_trace_events e
                          WHERE e.run_id = r.run_id AND e.phase = 'user'
                          ORDER BY e.started_at, e.id LIMIT 1),
                         '历史运行（未记录问题）') AS title
                FROM runs r JOIN threads t ON t.thread_id = r.thread_id
                WHERE r.run_id = ? AND substr(r.thread_id, 1, ?) = ?
                """, (run_id, len(owner_prefix), owner_prefix),
            ).fetchone()
            if row is None:
                return None
            events = self._conn.execute(
                """
                SELECT id, phase, label, status, started_at, finished_at
                FROM agent_trace_events
                WHERE run_id = ? AND thread_id = ?
                ORDER BY started_at, id LIMIT 500
                """, (run_id, row["thread_id"]),
            ).fetchall()
        return {**dict(row), "events": [dict(event) for event in events]}

    def fail_open_agent_trace_events(self, *, run_id: str) -> None:
        """运行异常退出时关闭仍在进行的阶段，避免界面永久显示运行中。"""

        with self._lock:
            self._conn.execute(
                """
                UPDATE agent_trace_events SET status = 'failed', finished_at = ?
                WHERE run_id = ? AND status = 'running'
                """, (utc_now(), run_id),
            )
            self._conn.commit()

    def clear_run_events(self, thread_id: str) -> None:
        """清空某个 thread 的临时过程事件。

        run_events 只服务当前/最近一次运行的过程展示；历史问答正文保存在
        thread_messages，不依赖这里的临时事件。
        """

        with self._lock:
            self._conn.execute("DELETE FROM run_events WHERE thread_id = ?", (thread_id,))
            self._conn.commit()

    def add_thread_message(
        self,
        *,
        message_id: str,
        thread_id: str,
        author: str,
        content: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """追加保存一条 dashboard 会话消息。

        thread_messages 保存的是用户能看到的问答正文，和 run_events 的过程步骤分开。
        这样继续输入新问题时不会覆盖上一轮问题和回答。
        """

        with self._lock:
            normalized_content = content.strip()
            if author == "user" and normalized_content:
                latest_user = self._conn.execute(
                    """
                    SELECT content
                    FROM thread_messages
                    WHERE thread_id = ?
                      AND author = 'user'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thread_id,),
                ).fetchone()
                if latest_user is not None and str(latest_user["content"]).strip() == normalized_content:
                    return
            self._conn.execute(
                """
                INSERT INTO thread_messages (
                  message_id, thread_id, run_id, author, content, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                  content=excluded.content,
                  metadata=excluded.metadata
                """,
                (
                    message_id,
                    thread_id,
                    run_id,
                    author,
                    normalized_content,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    utc_now(),
                ),
            )
            self._conn.commit()

    def list_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """按写入顺序读取 dashboard 会话消息。"""

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM thread_messages
                WHERE thread_id = ?
                ORDER BY created_at ASC
                """,
                (thread_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_thread_plan(
        self,
        *,
        plan_id: str,
        thread_id: str,
        prompt: str,
        plan_text: str,
        plan_path: str,
        run_id: str | None = None,
        status: str = "pending",
    ) -> None:
        """保存一份编码前技术方案。

        plan_text 用于前端快速展示；plan_path 指向 data/plans 下的 Markdown 文件，
        方便直接打开，也方便后续让 Agent 读取已确认方案。
        """

        with self._lock:
            now = utc_now()
            self._conn.execute(
                """
                INSERT INTO thread_plans (
                  plan_id, thread_id, run_id, status, prompt, plan_text, plan_path, created_at, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(plan_id) DO UPDATE SET
                  status=excluded.status,
                  prompt=excluded.prompt,
                  plan_text=excluded.plan_text,
                  plan_path=excluded.plan_path
                """,
                (plan_id, thread_id, run_id, status, prompt.strip(), plan_text.strip(), plan_path, now),
            )
            self._conn.commit()

    def get_latest_thread_plan(
        self,
        thread_id: str,
        *,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """读取某个 thread 最新一份技术方案。"""

        with self._lock:
            if status is None:
                row = self._conn.execute(
                    """
                    SELECT *
                    FROM thread_plans
                    WHERE thread_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thread_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """
                    SELECT *
                    FROM thread_plans
                    WHERE thread_id = ?
                      AND status = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thread_id, status),
                ).fetchone()
            return self._row_to_dict(row)

    def list_thread_plans(self, thread_id: str) -> list[dict[str, Any]]:
        """按创建顺序读取某个 thread 的方案历史。"""

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM thread_plans
                WHERE thread_id = ?
                ORDER BY created_at ASC
                """,
                (thread_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def approve_thread_plan(self, plan_id: str) -> dict[str, Any] | None:
        """把指定方案标记为已确认，并返回确认后的方案记录。"""

        with self._lock:
            now = utc_now()
            self._conn.execute(
                """
                UPDATE thread_plans
                SET status = 'approved',
                    approved_at = ?
                WHERE plan_id = ?
                """,
                (now, plan_id),
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM thread_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            return self._row_to_dict(row)

    def finish_open_run_events(self, thread_id: str, *, status: str = "completed") -> None:
        """把仍处于运行中的展示事件收尾。

        Agent 的官方 tool_calls 流有时只发起始事件，真正完成状态由工具内部事件记录。
        为避免前端在任务结束后还显示“运行中...”，任务完成或失败时统一关闭残留事件。
        """

        with self._lock:
            self._conn.execute(
                """
                UPDATE run_events
                SET status = ?,
                    updated_at = ?
                WHERE thread_id = ?
                  AND status IN ('pending', 'in_progress')
                """,
                (status, utc_now(), thread_id),
            )
            self._conn.commit()

    def get_latest_run(self, thread_id: str) -> dict[str, Any] | None:
        """读取某个 thread 最近一次运行记录。

        Dashboard 摘要需要把失败原因展示给前端，否则用户只能看到 error 状态，
        不知道是模型、Git、Gitee 还是本地权限导致的问题。
        """

        with self._lock:
            row = self._conn.execute(
                """
                SELECT *
                FROM runs
                WHERE thread_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def list_run_monitor(
        self, *, owner_prefix: str, limit: int = 50, offset: int = 0,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """只返回当前用户的运行摘要，可按会话筛选；逐轮标题不复用会话标题。"""

        with self._lock:
            run_filter = "substr(r.thread_id, 1, ?) = ?"
            run_params: tuple[Any, ...] = (len(owner_prefix), owner_prefix)
            if thread_id is not None:
                run_filter += " AND r.thread_id = ?"
                run_params += (thread_id,)
            sessions = self._conn.execute(
                """
                SELECT t.thread_id, t.title, COUNT(r.run_id) AS run_count,
                       MAX(r.started_at) AS latest_run_at
                FROM threads t JOIN runs r ON r.thread_id = t.thread_id
                WHERE substr(t.thread_id, 1, ?) = ?
                GROUP BY t.thread_id, t.title
                ORDER BY latest_run_at DESC
                """, (len(owner_prefix), owner_prefix),
            ).fetchall()
            summary = self._conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN r.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                       SUM(CASE WHEN r.status = 'running' THEN 1 ELSE 0 END) AS running,
                       AVG(CASE WHEN r.finished_at IS NOT NULL THEN
                           {self._duration_ms_sql()}
                       END) AS avg_duration_ms
                FROM runs r
                WHERE {run_filter}
                """,
                run_params,
            ).fetchone()
            rows = self._conn.execute(
                f"""
                SELECT r.run_id, r.thread_id, r.status, r.started_at,
                       r.finished_at, r.error, t.title AS session_title,
                       COALESCE(NULLIF(TRIM(r.user_question), ''),
                         (SELECT e.label FROM agent_trace_events e
                          WHERE e.run_id = r.run_id AND e.phase = 'user'
                          ORDER BY e.started_at, e.id LIMIT 1),
                         '历史运行（未记录问题）') AS title
                FROM runs r
                JOIN threads t ON t.thread_id = r.thread_id
                WHERE {run_filter}
                ORDER BY r.started_at DESC, r.run_id DESC
                LIMIT ? OFFSET ?
                """,
                (*run_params, limit, offset),
            ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            item["duration_ms"] = None
            if item["finished_at"]:
                try:
                    started = datetime.fromisoformat(item["started_at"])
                    finished = datetime.fromisoformat(item["finished_at"])
                    item["duration_ms"] = max(0, round((finished - started).total_seconds() * 1000))
                except ValueError:
                    pass
            items.append(item)
        return {
            "total": int(summary["total"]),
            "limit": limit,
            "offset": offset,
            "sessions": [dict(session) for session in sessions],
            "summary": {
                "completed": int(summary["completed"] or 0),
                "failed": int(summary["failed"] or 0),
                "running": int(summary["running"] or 0),
                "avg_duration_ms": round(summary["avg_duration_ms"] or 0),
            },
            "items": items,
        }

    @staticmethod
    def _duration_ms_sql() -> str:
        return "(julianday(r.finished_at) - julianday(r.started_at)) * 86400000"

    def delete_thread(self, thread_id: str) -> bool:
        """删除一个 dashboard 会话及其业务附属记录。

        这里清理的是业务 Store，不直接清理 LangGraph checkpoint。
        当前列表页只读取 threads/runs/review_findings，
        所以删除这些记录后，前端侧边栏会立即干净。
        """

        with self._lock:
            existing = self.get_thread(thread_id)
            if existing is None:
                return False
            self._conn.execute("DELETE FROM risk_audit_findings WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM risk_audit_results WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM review_findings WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM thread_plans WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM thread_messages WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM run_events WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM agent_trace_events WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM runs WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
            self._conn.commit()
            return True

    def save_risk_audit_result(
        self,
        *,
        result_id: str,
        run_id: str,
        thread_id: str,
        payload: dict[str, Any],
        report_markdown: str,
        answer_hash: str,
    ) -> dict[str, Any]:
        """原子保存一次结构化金融初筛结果及其风险线索。"""

        with self._lock:
            now = utc_now()
            previous = self._conn.execute(
                "SELECT result_id FROM risk_audit_results WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if previous is not None:
                self._conn.execute(
                    "DELETE FROM risk_audit_findings WHERE result_id = ?",
                    (previous["result_id"],),
                )
                self._conn.execute("DELETE FROM risk_audit_results WHERE run_id = ?", (run_id,))
            self._conn.execute(
                """
                INSERT INTO risk_audit_results (
                  result_id, run_id, thread_id, company_code, company_name, year,
                  status, summary, evidence_gaps, report_markdown, answer_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    run_id,
                    thread_id,
                    payload["company_code"],
                    payload["company_name"],
                    payload["year"],
                    payload["status"],
                    payload["summary"],
                    json.dumps(payload.get("evidence_gaps") or [], ensure_ascii=False),
                    report_markdown,
                    answer_hash,
                    now,
                ),
            )
            for ordinal, finding in enumerate(payload.get("findings") or [], start=1):
                finding_id = f"{result_id}-finding-{ordinal}"
                self._conn.execute(
                    """
                    INSERT INTO risk_audit_findings (
                      id, result_id, thread_id, ordinal, risk_type, severity, conclusion,
                      evidence_ids, data_points, uncertainty, review_question, review_status,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?)
                    """,
                    (
                        finding_id,
                        result_id,
                        thread_id,
                        ordinal,
                        finding["risk_type"],
                        finding["severity"],
                        finding["conclusion"],
                        json.dumps(finding.get("evidence_ids") or [], ensure_ascii=False),
                        json.dumps(finding.get("data_points") or [], ensure_ascii=False),
                        finding["uncertainty"],
                        finding["review_question"],
                        now,
                        now,
                    ),
                )
            self._conn.commit()
            saved = self.get_risk_audit_result(result_id)
            if saved is None:
                raise RuntimeError("结构化风险初筛结果保存失败")
            return saved

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        if not isinstance(value, str):
            return []
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []

    def get_risk_audit_result(self, result_id: str) -> dict[str, Any] | None:
        """读取一次结构化结果，并附上按顺序排列的 findings。"""

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM risk_audit_results WHERE result_id = ?",
                (result_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["evidence_gaps"] = self._json_list(result.get("evidence_gaps"))
            findings = self._conn.execute(
                "SELECT * FROM risk_audit_findings WHERE result_id = ? ORDER BY ordinal ASC",
                (result_id,),
            ).fetchall()
            result["findings"] = []
            for finding_row in findings:
                finding = dict(finding_row)
                finding["evidence_ids"] = self._json_list(finding.get("evidence_ids"))
                finding["data_points"] = self._json_list(finding.get("data_points"))
                result["findings"].append(finding)
            return result

    def list_risk_audit_results(self, thread_id: str) -> list[dict[str, Any]]:
        """按运行时间读取一个会话的全部结构化初筛结果。"""

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT result_id
                FROM risk_audit_results
                WHERE thread_id = ?
                ORDER BY created_at ASC
                """,
                (thread_id,),
            ).fetchall()
            return [
                result
                for row in rows
                if (result := self.get_risk_audit_result(str(row["result_id"]))) is not None
            ]

    def add_finding(
        self,
        *,
        finding_id: str,
        thread_id: str,
        file: str,
        line: int | None,
        severity: str,
        title: str,
        description: str,
        status: str = "open",
    ) -> None:
        with self._lock:
            now = utc_now()
            self._conn.execute(
                """
                INSERT INTO review_findings (
                  id, thread_id, file, line, severity, title, description, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  file=excluded.file,
                  line=excluded.line,
                  severity=excluded.severity,
                  title=excluded.title,
                  description=excluded.description,
                  status=excluded.status,
                  updated_at=excluded.updated_at
                """,
                (finding_id, thread_id, file, line, severity, title, description, status, now, now),
            )
            self._conn.commit()

    def list_findings(self, thread_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM review_findings WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, json.dumps(value, ensure_ascii=False), utc_now()),
            )
            self._conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            return json.loads(row["value"])
