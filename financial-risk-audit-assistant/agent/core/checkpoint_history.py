from __future__ import annotations

import logging
import re
from hashlib import sha1
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent.core.graph import get_checkpointer
from agent.financial.citations import citations_from_tool_message
from agent.financial.risk_result import strip_risk_result_block

logger = logging.getLogger("agent.checkpoint_history")


def _content_to_text(content: Any) -> str:
    """把 LangChain message.content 转成普通文本。

    DeepSeek / OpenAI 兼容模型在 LangChain 1.x 中可能返回字符串，也可能返回
    content block 列表，例如 `[{"type": "text", "text": "..."}]`。这里统一抽取
    text 字段，避免前端看到 Python 对象 repr。
    """

    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return str(content).strip()


def _delta_messages_from_checkpoint(thread_id: str) -> list[Any]:
    """读取某个 thread 的 messages 通道历史。

    `SqliteSaver.get_tuple()` 的最新快照不一定直接包含 `channel_values["messages"]`。
    DeepAgents / LangGraph 新版本会把通道历史保存在 delta channel 里，所以这里使用
    `get_delta_channel_history(config, channels=["messages"])` 读取 seed + writes。

    注意：seed 是一个基础快照，writes 是后续增量。不同版本可能重复返回同一条消息，
    后续会按 role/content/message_id 去重。
    """

    checkpointer = get_checkpointer()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        history = checkpointer.get_delta_channel_history(config=config, channels=["messages"])
    except Exception:
        logger.exception("读取 checkpoint messages 通道失败：thread_id=%s", thread_id)
        return []

    channel_history = history.get("messages") if isinstance(history, dict) else None
    if not isinstance(channel_history, dict):
        channel_history = {}

    messages: list[Any] = []
    seed = channel_history.get("seed")
    # langgraph-checkpoint-sqlite 不同版本返回的 seed 形态不同：
    # - 旧版：带 `.value` 属性的对象；
    # - 当前版：直接返回完整的 message list。
    # 旧实现只处理第一种，因此升级依赖后刷新会得到空历史，虽然 SQLite 中的数据仍在。
    seed_value = seed if isinstance(seed, list) else getattr(seed, "value", None)
    if isinstance(seed_value, list):
        messages.extend(seed_value)

    writes = channel_history.get("writes")
    if isinstance(writes, list):
        for write in writes:
            if not isinstance(write, tuple) or len(write) < 3:
                continue
            value = write[2]
            if isinstance(value, list):
                messages.extend(value)
            elif value is not None:
                messages.append(value)

    if messages:
        return messages

    # 某些 checkpointer 实现不提供 delta history，但最新 checkpoint 的
    # channel_values 中仍保存完整 messages。这里作为兼容兜底，避免持久化数据存在、
    # 页面刷新却显示空会话。
    try:
        checkpoint_tuple = checkpointer.get_tuple(config)
    except Exception:
        logger.exception("读取最新 checkpoint 失败：thread_id=%s", thread_id)
        return []
    if checkpoint_tuple is None:
        return []
    checkpoint = getattr(checkpoint_tuple, "checkpoint", None)
    if not isinstance(checkpoint, dict):
        return []
    channel_values = checkpoint.get("channel_values")
    if not isinstance(channel_values, dict):
        return []
    latest_messages = channel_values.get("messages")
    return list(latest_messages) if isinstance(latest_messages, list) else []


def _extract_user_prompt(text: str) -> str:
    """从 runtime 包装后的 HumanMessage 中还原用户原始输入。

    后端真正发给 Agent 的用户内容会包含仓库地址、任务类型和执行规则，例如：
    `Gitee 仓库地址... 用户任务：... 这是只读任务...`。
    前端历史不应该展示这些内部包装文本，只展示用户在输入框里写的原始需求。
    """

    normalized = text.strip()
    if not normalized:
        return ""

    # 当前项目的前端历史只从 checkpoint 恢复。对于“确认实施”这类 follow-up
    # 指令，runtime 会把真正执行目标改写成上一轮技术方案和内部规则；如果只从
    # “用户任务：”提取，网页历史就会丢失用户刚刚输入的“确认实施”。因此 runtime
    # 会额外写入“用户可见输入”，这里必须优先读取它。
    if "用户可见输入：" in normalized:
        tail = normalized.split("用户可见输入：", 1)[1].strip()
        stop_patterns = [
            "\n\n内部执行上下文：",
            "\n\nGitee 仓库地址：",
            "\n\n任务类型：",
            "\n\n用户任务：",
        ]
        for stop in stop_patterns:
            if stop in tail:
                tail = tail.split(stop, 1)[0].strip()
        return tail

    # 先处理“用户新的修改要求”，因为修订方案的 HumanMessage 往往同时包含
    # “原始用户需求”“上一版技术方案”“用户新的修改要求”。如果先匹配“用户需求”，
    # 会误把后面的大段内部包装内容也当成用户输入展示到网页历史里。
    if "用户新的修改要求：" in normalized:
        tail = normalized.rsplit("用户新的修改要求：", 1)[1].strip()
        # “用户新的修改要求”后面还会拼接专门给方案 Agent 的内部规则。
        # 这些规则只用于约束模型，不属于用户在输入框里的原始问题，不能展示到网页。
        stop_patterns = [
            "\n\n请基于上一版方案",
            "\n\n不要只输出差异说明",
            "\n\n请只生成技术方案",
            "\n\n方案必须使用中文 Markdown",
            "\n\n最后必须单独输出一句",
        ]
        for stop in stop_patterns:
            if stop in tail:
                tail = tail.split(stop, 1)[0].strip()
        return tail

    markers = ["用户任务：", "原始用户需求：", "用户需求："]
    for marker in markers:
        if marker not in normalized:
            continue
        tail = normalized.split(marker, 1)[1].strip()
        stop_patterns = [
            "\n\n这是只读任务",
            "\n\n这是开发实现任务",
            "\n\n请只生成技术方案",
            "\n\n用户已经确认以下技术方案",
            "\n\n任务类型：",
        ]
        for stop in stop_patterns:
            if stop in tail:
                tail = tail.split(stop, 1)[0].strip()
        return tail

    return normalized


def _has_visible_markdown_value(text: str) -> bool:
    """判断非最终 assistant 消息是否值得作为历史过程展示。

    DeepAgents 会产生很多很短的过程消息，例如“现在读取文件”。这些已经通过
    V3 event streaming 和 run_events 展示过，不应该在历史正文里堆积。
    """

    if len(text) >= 200:
        return True
    value_markers = [
        "# ",
        "## ",
        "技术方案",
        "代码审查报告",
        "审查报告",
        "完成总结",
        "任务完成总结",
        "内容如下",
        "整体架构",
    ]
    return any(marker in text for marker in value_markers)


def _final_assistant_indexes(messages: list[Any]) -> set[int]:
    """Locate the last text answer in each user turn, independent of its length."""
    final_indexes: set[int] = set()
    candidate: int | None = None
    for index, message in enumerate(messages):
        role = _message_role(message)
        if role == "user":
            if candidate is not None:
                final_indexes.add(candidate)
            candidate = None
        elif role == "agent":
            if (getattr(message, "tool_calls", None)
                    or getattr(message, "invalid_tool_calls", None)
                    or (getattr(message, "additional_kwargs", None) or {}).get("tool_calls")
                    or (getattr(message, "response_metadata", None) or {}).get("finish_reason") == "tool_calls"):
                continue
            if strip_risk_result_block(_content_to_text(getattr(message, "content", None))).strip():
                candidate = index
    if candidate is not None:
        final_indexes.add(candidate)
    return final_indexes


def _message_role(message: Any) -> str | None:
    """识别 LangChain 消息角色。"""

    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "agent"
    if isinstance(message, BaseMessage):
        message_type = str(message.type or "").lower()
        if message_type in {"human", "user"}:
            return "user"
        if message_type in {"ai", "assistant"}:
            return "agent"
    return None


def _dedupe_key(author: str, content: str) -> tuple[str, str]:
    """按内容生成去重键。

    checkpoint 的 seed + writes 里，同一条正文可能带不同 message id。
    因此前端可见历史必须按 author + content 去重，而不是按消息对象 id 去重。
    """

    return author, _compact_content(content)


def _compact_content(content: str) -> str:
    """把正文压缩成稳定去重文本。

    checkpoint 的 seed 和 writes 可能重复返回同一条可见消息，也可能因为换行、
    多个空格等格式差异导致文本看起来不同。这里把空白统一压缩后再参与去重和
    稳定 id 计算，避免前端历史出现重复气泡。
    """

    return re.sub(r"\s+", " ", (content or "").strip())


def stable_history_message_id(thread_id: str, author: str, content: str, occurrence: int = 1) -> str:
    """为前端历史消息生成稳定 id。

    旧实现用列表 index 作为 id，checkpoint 新增消息后 index 会变化，前端容易把旧消息
    当成新消息或被当前过程块覆盖。这里改成 thread_id + author + content hash，
    同一条历史正文在多次 SSE 快照中保持同一个 id。
    """

    digest = sha1(f"{author}\n{_compact_content(content)}".encode("utf-8")).hexdigest()[:16]
    suffix = f"-{occurrence}" if occurrence > 1 else ""
    return f"{thread_id}-history-{author}-{digest}{suffix}"


def visible_checkpoint_messages(thread_id: str) -> list[dict[str, Any]]:
    """读取并整理某个 thread 的用户可见历史消息。

    返回值只包含前端真正需要展示的 user/agent 正文：
    - user：尽量还原输入框里的原始文本。
    - agent：每轮最终回复无论长短都保留，较长的过程仍可展示。
    - tool/system/短过程消息：过滤。

    如果 checkpoint 读取失败或没有可用消息，返回空列表。前端历史不再回退读取 Store，
    Store 只保存任务摘要、运行状态、review findings 等业务数据。
    """

    visible: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    occurrences: dict[tuple[str, str], int] = {}
    pending_citations: list[dict[str, Any]] = []
    seen_citation_sources: dict[int, tuple[Any, ...]] = {}
    conflicting_citation_ids: set[int] = set()

    messages = _delta_messages_from_checkpoint(thread_id)
    final_assistant_indexes = _final_assistant_indexes(messages)
    for index, message in enumerate(messages):
        if isinstance(message, ToolMessage):
            by_key = {
                (item["kind"], item["doc_id"], item["page"], item["snippet"]): item
                for item in pending_citations
            }
            for item in citations_from_tool_message(message):
                citation_id = item["citation_id"]
                source = (item["kind"], item["doc_id"], item["page"], item["snippet"])
                previous = seen_citation_sources.setdefault(citation_id, source)
                if previous != source:
                    conflicting_citation_ids.add(citation_id)
                by_key.setdefault(
                    (item["kind"], item["doc_id"], item["page"], item["snippet"]),
                    item,
                )
            pending_citations = list(by_key.values())
            continue
        role = _message_role(message)
        if role is None:
            continue
        text = _content_to_text(getattr(message, "content", None))
        if not text:
            continue

        if role == "user":
            # Deduplicate checkpoint seed/writes within a turn, not across
            # separate questions: users may ask the same thing twice.
            seen.clear()
            pending_citations = []
            conflicting_citation_ids = set()
            text = _extract_user_prompt(text)
        else:
            text = strip_risk_result_block(text)
            if index not in final_assistant_indexes and not _has_visible_markdown_value(text):
                continue

        text = text.strip()
        if not text:
            continue
        key = _dedupe_key(role, text)
        if key in seen:
            continue
        seen.add(key)
        occurrences[key] = occurrences.get(key, 0) + 1
        visible_message = {
                "message_id": stable_history_message_id(thread_id, role, text, occurrences[key]),
                "author": role,
                "content": text,
                "source": "checkpoint",
            }
        if role == "agent" and pending_citations:
            visible_message["citations"] = [
                item for item in pending_citations
                if item["citation_id"] not in conflicting_citation_ids
            ]
            if conflicting_citation_ids:
                visible_message["citation_conflicts"] = sorted(conflicting_citation_ids)
        visible.append(visible_message)

    return visible
