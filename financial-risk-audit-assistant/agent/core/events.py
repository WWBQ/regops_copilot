from __future__ import annotations

import logging

logger = logging.getLogger("agent.run.events")


def _get_event_store():
    """运行事件与会话详情共用 PostgreSQL 业务 Store。

    延迟导入，避免 graph、runtime 和工具模块初始化时循环导入。
    """

    from agent.core.graph import get_store

    return get_store()


def record_event(
    thread_id: str,
    key: str,
    title: str,
    *,
    kind: str = "think",
    status: str = "in_progress",
    detail: str | None = None,
) -> None:
    """写入一个可展示在前端的运行步骤。

    这个模块独立于 runtime，避免 tools 导入 runtime 时形成循环依赖。
    """

    try:
        _get_event_store().add_run_event(
            event_id=f"{thread_id}:{key}",
            thread_id=thread_id,
            kind=kind,
            title=title,
            status=status,
            detail=detail,
        )
    except Exception:
        # 步骤记录只服务于展示，存储瞬时异常不能中断真正的 Agent 任务。
        logger.exception("记录运行步骤失败：thread_id=%s key=%s title=%s", thread_id, key, title)
