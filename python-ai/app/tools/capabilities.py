"""契约自省：能力树 + 单工具 Schema。"""

from __future__ import annotations

from typing import Any

from app.tools.registry import list_tool_specs

_READ = {
    "lookup_metric",
    "list_scope",
    "rag_search",
    "verify_number",
    "compare_peers",
}
_WRITE = {"create_review_draft"}
_VALIDATE = {"emit_conclusion"}


def tool_capabilities() -> dict[str, Any]:
    commands = []
    for spec in list_tool_specs():
        if spec.name in _WRITE:
            kind = "write"
        elif spec.name in _VALIDATE:
            kind = "validate"
        else:
            kind = "read"
        commands.append(
            {
                "name": spec.name,
                "kind": kind,
                "description": spec.description,
                "input_schema": spec.args_model.model_json_schema(),
            }
        )
    return {
        "kind": "agent-capabilities",
        "wired_to_chat": True,
        "chat_entry": "intent",
        "chat_intents": ["opt_in", "overview", "unsupported_topic", "blocked_followup"],
        "wired_to_graph": True,
        "rules": "docs/AGENT_RULES.md",
        "commands": commands,
        "forbidden": [
            "execute_sql",
            "direct_http",
            "client_truncate",
            "invent_missing_metric",
            "compute_ratio",
        ],
        "must": [
            "list_scope_before_unknown_company_or_concept",
            "stop_when_ok_false",
            "cite_doc_id_and_page_for_rag",
            "checkpoint_before_emit_conclusion",
            "confirm_before_create_review_draft",
            "review_draft_pending_only",
            "stop_on_budget_exceeded",
            "maker_checker_via_java",
        ],
    }


def tool_schema(name: str) -> dict[str, Any] | None:
    spec = next((item for item in list_tool_specs() if item.name == name), None)
    if spec is None:
        return None
    return spec.mcp_schema()
