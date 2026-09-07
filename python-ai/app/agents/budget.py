"""w6-5：步数 / 工具次数 / 时间 / Token 预算。超限终止，写工具失败不盲重试。"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Literal

from app.config import get_settings
from app.schemas.tools import ToolInvokeResponse

BudgetKind = Literal["steps", "tool_calls", "time_ms", "tokens", "rounds", "lookup_metric"]

FALLBACK: dict[str, str] = {
    "missing": "缺数或覆盖面不足，已停止，不插值、不编造。",
    "unauthorized": "越权访问，已停止。",
    "timeout": "工具超时，已停止，请稍后重试或转人工。未写入工单。",
    "budget_exceeded": "超过步数/工具/时间/Token 预算，已终止，未写入工单。",
    "forbidden_write": "写操作未确认或未开放，未落库。",
    "handler_error": "工具失败，已停止，不重试写。",
    "unknown_tool": "未知或未授权工具，已停止。",
}

_KIND_ZH = {
    "steps": "步数",
    "tool_calls": "工具次数",
    "time_ms": "时间",
    "tokens": "Token",
    "rounds": "模型轮次",
    "lookup_metric": "lookup_metric 次数",
}


@dataclass(frozen=True)
class BudgetLimits:
    max_steps: int = 12
    max_tool_calls: int = 8
    max_time_ms: float = 120_000.0
    max_tokens: int = 8_000
    max_rounds: int = 4
    max_lookup_metric: int = 1
    loop_max_tool_calls: int = 6
    loop_max_time_ms: float = 120_000.0

    @classmethod
    def from_settings(cls) -> BudgetLimits:
        settings = get_settings()
        return cls(
            max_steps=int(settings.workflow_max_steps),
            max_tool_calls=int(settings.workflow_max_tool_calls),
            max_time_ms=float(settings.workflow_max_time_ms),
            max_tokens=int(settings.tool_loop_max_tokens),
            max_rounds=int(settings.tool_loop_max_rounds),
            max_lookup_metric=int(settings.tool_loop_max_lookup_metric),
            loop_max_tool_calls=int(settings.tool_loop_max_tool_calls),
            loop_max_time_ms=float(settings.tool_loop_max_time_ms),
        )


@dataclass
class BudgetMeter:
    limits: BudgetLimits
    started: float
    tool_calls: int = 0
    tokens: int = 0
    rounds: int = 0
    lookups: int = 0

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started) * 1000

    def reject_tool(self, name: str) -> BudgetKind | None:
        if self.elapsed_ms() >= self.limits.max_time_ms:
            return "time_ms"
        if self.tool_calls >= self.limits.max_tool_calls:
            return "tool_calls"
        if name == "lookup_metric" and self.lookups >= self.limits.max_lookup_metric:
            return "lookup_metric"
        return None

    def reject_loop_tool(self, name: str) -> BudgetKind | None:
        if self.elapsed_ms() >= self.limits.loop_max_time_ms:
            return "time_ms"
        if self.tool_calls >= self.limits.loop_max_tool_calls:
            return "tool_calls"
        if name == "lookup_metric" and self.lookups >= self.limits.max_lookup_metric:
            return "lookup_metric"
        return None

    def reject_round(self) -> BudgetKind | None:
        if self.elapsed_ms() >= self.limits.loop_max_time_ms:
            return "time_ms"
        if self.tokens >= self.limits.max_tokens:
            return "tokens"
        if self.rounds >= self.limits.max_rounds:
            return "rounds"
        return None

    def note_tool(self, name: str) -> None:
        self.tool_calls += 1
        if name == "lookup_metric":
            self.lookups += 1

    def note_tokens(self, prompt: int, completion: int) -> None:
        self.tokens += max(0, int(prompt)) + max(0, int(completion))

    def note_round(self) -> None:
        self.rounds += 1


_limits: ContextVar[BudgetLimits | None] = ContextVar("regops_budget_limits", default=None)
_meter: ContextVar[BudgetMeter | None] = ContextVar("regops_budget_meter", default=None)


def current_limits() -> BudgetLimits:
    return _limits.get() or BudgetLimits.from_settings()


def current_meter() -> BudgetMeter | None:
    return _meter.get()


def budget_message(kind: BudgetKind) -> str:
    label = _KIND_ZH.get(kind, kind)
    return f"超过{label}预算，已终止，未写入工单。不重试写操作。"


def classify_error(out: ToolInvokeResponse) -> str | None:
    if out.ok:
        return None
    code = out.error_code or "handler_error"
    if code == "budget_exceeded":
        return out.error or FALLBACK["budget_exceeded"]
    return FALLBACK.get(code)


def budget_response(name: str, kind: BudgetKind, *, request_id: str | None = None) -> ToolInvokeResponse:
    return ToolInvokeResponse(
        name=name,
        ok=False,
        stop=True,
        result={},
        error=budget_message(kind),
        error_code="budget_exceeded",
        request_id=request_id,
    )


@contextmanager
def use_limits(limits: BudgetLimits | None = None, *, reset_meter: bool = True) -> Iterator[BudgetMeter]:
    resolved = limits or current_limits()
    token_limits = _limits.set(resolved)
    meter = BudgetMeter(limits=resolved, started=time.monotonic()) if reset_meter or _meter.get() is None else _meter.get()
    assert meter is not None
    token_meter = _meter.set(meter)
    try:
        yield meter
    finally:
        _meter.reset(token_meter)
        _limits.reset(token_limits)


def guard_tool(name: str, invoke, /, *args, request_id: str | None = None, **kwargs) -> ToolInvokeResponse:
    meter = current_meter()
    if meter is not None:
        kind = meter.reject_tool(name)
        if kind:
            return budget_response(name, kind, request_id=request_id)
    out = invoke(*args, **kwargs)
    if meter is not None:
        meter.note_tool(name)
    if isinstance(out, ToolInvokeResponse) and not out.ok:
        message = classify_error(out)
        if message and out.error != message:
            return out.model_copy(update={"error": message})
    return out
