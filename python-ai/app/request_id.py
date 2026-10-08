"""W9：X-Request-ID + W3C traceparent（ASGI，不缓冲 SSE）。"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar
from typing import Any
from uuid import UUID, uuid4

REQUEST_ID_HEADER = b"x-request-id"
TRACEPARENT_HEADER = b"traceparent"
USER_HEADER = b"x-regops-user"
_TRACEPARENT_RE = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")
_span_id_ctx: ContextVar[str] = ContextVar("span_id", default="-")
_traceparent_ctx: ContextVar[str] = ContextVar("traceparent", default="")
_user_id_ctx: ContextVar[str | None] = ContextVar("regops_user_id", default=None)

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


def current_request_id() -> str:
    return _request_id_ctx.get() or "-"


def current_trace_id() -> str:
    return _trace_id_ctx.get() or "-"


def current_span_id() -> str:
    return _span_id_ctx.get() or "-"


def current_traceparent() -> str:
    return _traceparent_ctx.get() or ""


def current_regops_user_id() -> str | None:
    return _user_id_ctx.get()


def mint_traceparent() -> str:
    trace_id = uuid4().hex
    span_id = uuid4().hex[:16]
    return f"00-{trace_id}-{span_id}-01"


def parse_traceparent(value: str | None) -> tuple[str, str, str] | None:
    text = (value or "").strip().lower()
    if not _TRACEPARENT_RE.match(text):
        return None
    _, trace_id, span_id, _flags = text.split("-", 3)
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return text, trace_id, span_id


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key == name:
            text = value.decode("utf-8", errors="ignore").strip()
            return text or None
    return None


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        record.trace_id = current_trace_id()
        return True


class RequestIdMiddleware:
    """注入 / 回写 X-Request-ID 与 traceparent，写入 contextvar 供日志与 Trace 使用。"""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = _header(scope, REQUEST_ID_HEADER) or str(uuid4())
        parsed = parse_traceparent(_header(scope, TRACEPARENT_HEADER))
        traceparent = parsed[0] if parsed else mint_traceparent()
        parsed = parsed or parse_traceparent(traceparent)
        assert parsed is not None
        _, trace_id, span_id = parsed

        rid_token = _request_id_ctx.set(request_id)
        tid_token = _trace_id_ctx.set(trace_id)
        sid_token = _span_id_ctx.set(span_id)
        tp_token = _traceparent_ctx.set(traceparent)
        raw_user_id = _header(scope, USER_HEADER)
        try:
            user_id = str(UUID(raw_user_id)) if raw_user_id else None
        except ValueError:
            user_id = None
        uid_token = _user_id_ctx.set(user_id)

        encoded_id = request_id.encode("utf-8")
        encoded_tp = traceparent.encode("utf-8")
        headers = [
            (key, value)
            for key, value in (scope.get("headers") or [])
            if key not in {REQUEST_ID_HEADER, TRACEPARENT_HEADER}
        ]
        headers.append((REQUEST_ID_HEADER, encoded_id))
        headers.append((TRACEPARENT_HEADER, encoded_tp))
        scope = dict(scope)
        scope["headers"] = headers

        async def send_with_id(message: MutableMapping[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                start_headers = [
                    (key, value)
                    for key, value in (message.get("headers") or [])
                    if key not in {REQUEST_ID_HEADER, TRACEPARENT_HEADER}
                ]
                start_headers.append((REQUEST_ID_HEADER, encoded_id))
                start_headers.append((TRACEPARENT_HEADER, encoded_tp))
                message = dict(message)
                message["headers"] = start_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _user_id_ctx.reset(uid_token)
            _request_id_ctx.reset(rid_token)
            _trace_id_ctx.reset(tid_token)
            _span_id_ctx.reset(sid_token)
            _traceparent_ctx.reset(tp_token)
