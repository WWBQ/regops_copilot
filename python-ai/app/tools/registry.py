"""工具注册表：OpenAI Function Calling 形态。执行走 live 或 mock。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.schemas.tools import (
    ComparePeersArgs,
    CreateReviewDraftArgs,
    EmitConclusionArgs,
    ListScopeArgs,
    LookupMetricArgs,
    RagSearchArgs,
    ToolContext,
    ToolInvokeResponse,
    VerifyNumberArgs,
)
from app.tools.compare import compare_peers_description, run_compare_peers
from app.tools.conclusion import emit_conclusion_description, run_emit_conclusion
from app.tools.draft import create_review_draft_description, run_create_review_draft
from app.tools.lookup import lookup_metric_description, run_lookup_metric
from app.tools.mock import replay_or_run
from app.tools.pii import mask_for_log
from app.tools.rag import rag_search_description, run_rag_search
from app.tools.scope import list_scope_description, run_list_scope
from app.tools.verify import verify_number_description, run_verify_number

logger = logging.getLogger(__name__)


class ToolSpec:
    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: Callable[[BaseModel], BaseModel],
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.handler = handler

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def mcp_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.args_model.model_json_schema(),
        }


def _specs() -> dict[str, ToolSpec]:
    return {
        "lookup_metric": ToolSpec(
            name="lookup_metric",
            description=lookup_metric_description(),
            args_model=LookupMetricArgs,
            handler=run_lookup_metric,  # type: ignore[arg-type]
        ),
        "list_scope": ToolSpec(
            name="list_scope",
            description=list_scope_description(),
            args_model=ListScopeArgs,
            handler=run_list_scope,  # type: ignore[arg-type]
        ),
        "rag_search": ToolSpec(
            name="rag_search",
            description=rag_search_description(),
            args_model=RagSearchArgs,
            handler=run_rag_search,  # type: ignore[arg-type]
        ),
        "verify_number": ToolSpec(
            name="verify_number",
            description=verify_number_description(),
            args_model=VerifyNumberArgs,
            handler=run_verify_number,  # type: ignore[arg-type]
        ),
        "compare_peers": ToolSpec(
            name="compare_peers",
            description=compare_peers_description(),
            args_model=ComparePeersArgs,
            handler=run_compare_peers,  # type: ignore[arg-type]
        ),
        "create_review_draft": ToolSpec(
            name="create_review_draft",
            description=create_review_draft_description(),
            args_model=CreateReviewDraftArgs,
            handler=run_create_review_draft,  # type: ignore[arg-type]
        ),
        "emit_conclusion": ToolSpec(
            name="emit_conclusion",
            description=emit_conclusion_description(),
            args_model=EmitConclusionArgs,
            handler=run_emit_conclusion,  # type: ignore[arg-type]
        ),
    }


def list_tool_specs() -> list[ToolSpec]:
    return list(_specs().values())


def openai_tool_schemas() -> list[dict[str, Any]]:
    return [spec.openai_schema() for spec in list_tool_specs()]


def mcp_tool_schemas() -> list[dict[str, Any]]:
    return [spec.mcp_schema() for spec in list_tool_specs()]


def _resolve_backend(ctx: ToolContext) -> str:
    if ctx.backend in {"live", "mock"}:
        return ctx.backend
    mode = (get_settings().tool_backend or "live").strip().lower()
    return "mock" if mode == "mock" else "live"


def invoke_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    context: ToolContext | None = None,
) -> ToolInvokeResponse:
    ctx = context or ToolContext()
    spec = _specs().get(name)
    if spec is None:
        return ToolInvokeResponse(
            name=name,
            ok=False,
            stop=True,
            result={},
            error=f"未知工具：{name}。不挂 execute_sql 或手算比率。",
            error_code="unknown_tool",
            request_id=ctx.request_id,
        )
    logger.info(
        "invoke_tool name=%s request_id=%s args=%s",
        name,
        ctx.request_id,
        mask_for_log(str(arguments or {})),
    )
    arguments = dict(arguments or {})
    if name == "create_review_draft":
        if ctx.dept and not arguments.get("dept"):
            arguments["dept"] = ctx.dept
        if ctx.idempotency_key and not arguments.get("thread_id"):
            arguments["thread_id"] = ctx.idempotency_key
        if ctx.request_id and not arguments.get("request_id"):
            arguments["request_id"] = ctx.request_id
    try:
        parsed = spec.args_model.model_validate(arguments)
    except ValidationError as exc:
        return ToolInvokeResponse(
            name=name,
            ok=False,
            stop=True,
            result={},
            error=exc.errors()[0].get("msg") if exc.errors() else str(exc),
            error_code="invalid_params",
            request_id=ctx.request_id,
        )
    if _resolve_backend(ctx) == "mock":
        return replay_or_run(name, parsed, ctx)
    try:
        result = spec.handler(parsed)
    except ValueError as exc:
        return ToolInvokeResponse(
            name=name,
            ok=False,
            stop=True,
            result={},
            error=str(exc),
            error_code="handler_error",
            request_id=ctx.request_id,
        )
    payload = result.model_dump()
    error_code = None
    if name == "create_review_draft" and not payload.get("ok"):
        error_code = "handler_error"
        if "不落库" in str(payload.get("message") or "") or "未开放" in str(payload.get("message") or ""):
            error_code = "forbidden_write"
    return ToolInvokeResponse(
        name=name,
        ok=bool(payload.get("ok")),
        stop=bool(payload.get("stop")),
        result=payload,
        error=None if payload.get("ok") else payload.get("message"),
        error_code=error_code,  # type: ignore[arg-type]
        replayed=bool(payload.get("replayed")),
        request_id=ctx.request_id,
    )
