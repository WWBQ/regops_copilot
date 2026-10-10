"""Thread-scoped, durable pointer to an AI Coding object-store snapshot."""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlsplit


def _identity(thread_id: str) -> tuple[tuple[str, ...], str]:
    user_id, separator, conversation_id = thread_id.partition("_coding_")
    try:
        if not separator or str(uuid.UUID(user_id)) != user_id or str(uuid.UUID(conversation_id)) != conversation_id:
            raise ValueError
    except ValueError as exc:
        raise ValueError("AI Coding 会话 ID 无效") from exc
    return ("ai-coding", "snapshots", user_id), conversation_id


def remember_snapshot(thread_id: str, *, uri: str, sha256: str) -> None:
    namespace, key = _identity(thread_id)
    _validate_uri(thread_id, uri)
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("快照哈希无效")
    from agent.core.graph import get_langgraph_store

    get_langgraph_store().put(namespace, key, {"object_uri": uri, "sha256": sha256})


def recall_snapshot(thread_id: str) -> dict[str, str] | None:
    namespace, key = _identity(thread_id)
    from agent.core.graph import get_langgraph_store

    item = get_langgraph_store().get(namespace, key)
    if item is None:
        return None
    value = item.value
    uri, sha256 = value.get("object_uri"), value.get("sha256")
    if not isinstance(uri, str) or not isinstance(sha256, str):
        raise RuntimeError("长期记忆中的沙箱快照引用无效")
    _validate_uri(thread_id, uri)
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise RuntimeError("长期记忆中的沙箱快照哈希无效")
    return {"object_uri": uri, "sha256": sha256}


def forget_snapshot(thread_id: str) -> None:
    namespace, key = _identity(thread_id)
    from agent.core.graph import get_langgraph_store

    get_langgraph_store().delete(namespace, key)


def _validate_uri(thread_id: str, uri: str) -> None:
    parsed = urlsplit(uri)
    expected_path = f"/coding-snapshots/{thread_id}.zip"
    if (parsed.scheme != "object" or not parsed.netloc or parsed.path != expected_path
            or parsed.query or parsed.fragment):
        raise ValueError("快照对象引用不属于当前会话")
