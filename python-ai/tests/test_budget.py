import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.budget import BudgetLimits, budget_message, use_limits
from app.agents.graph import run_review_workflow
from app.agents.tool_loop import run_tool_loop
from app.models.base import ChatResult
from app.schemas.tools import ToolInvokeResponse
from tests.test_agents import _ScriptedLLM, _fail, _scripted_tools

QUESTION = "对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论"


def test_workflow_stops_when_tool_budget_exceeded(monkeypatch):
    monkeypatch.setattr("app.agents.graph.call_tool", _scripted_tools())
    with use_limits(BudgetLimits(max_tool_calls=2)):
        out = run_review_workflow(QUESTION, checkpointer=InMemorySaver(), dept="research")
    assert out.route == "agent_blocked"
    assert out.stop_reason != "cancelled"
    assert "预算" in (out.reply or "") or "预算" in (out.stop_reason or "")
    tools = [item.get("tool") for item in out.trace if item.get("tool")]
    assert "emit_conclusion" not in tools
    assert "create_review_draft" not in tools
    assert out.draft_id is None


def test_workflow_stops_when_time_budget_exceeded(monkeypatch):
    monkeypatch.setattr("app.agents.graph.call_tool", _scripted_tools())
    with use_limits(BudgetLimits(max_time_ms=0)):
        out = run_review_workflow(QUESTION, checkpointer=InMemorySaver(), dept="research")
    assert out.route == "agent_blocked"
    assert "预算" in (out.reply or "") or "时间" in (out.reply or "")
    assert "emit_conclusion" not in [item.get("tool") for item in out.trace]


def test_timeout_degrades_to_human_and_does_not_write(monkeypatch):
    monkeypatch.setattr(
        "app.agents.graph.call_tool",
        _scripted_tools(
            compare_peers=_fail(
                "compare_peers",
                "upstream timeout",
                error_code="timeout",
            )
        ),
    )
    out = run_review_workflow(QUESTION, checkpointer=InMemorySaver(), dept="research")
    assert out.route == "agent_blocked"
    assert "超时" in out.reply
    assert "转人工" in out.reply
    assert "create_review_draft" not in [item.get("tool") for item in out.trace]


def test_resume_does_not_retry_write_after_done(monkeypatch):
    base = _scripted_tools()
    calls: list[str] = []

    def tracked(name, arguments, request_id=None, **_kwargs):
        calls.append(name)
        return base(name, arguments, request_id)

    monkeypatch.setattr("app.agents.graph.call_tool", tracked)
    saver = InMemorySaver()
    paused = run_review_workflow(QUESTION, checkpointer=saver, dept="research")
    assert paused.route == "agent_paused"
    done = run_review_workflow(
        "确认",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="research",
        action="resume",
    )
    assert done.route == "agent"
    assert calls.count("create_review_draft") == 1
    again = run_review_workflow(
        "确认",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="research",
        action="resume",
    )
    assert again.route == "agent"
    assert calls.count("create_review_draft") == 1
    assert calls.count("emit_conclusion") == 1


def test_budget_message_is_explicit():
    text = budget_message("tool_calls")
    assert "预算" in text
    assert "未写入" in text


def test_tool_loop_stops_on_token_budget():
    client = _ScriptedLLM([ChatResult(content="不该生成")])
    with use_limits(BudgetLimits(max_tokens=0)):
        out = asyncio.run(run_tool_loop("格力2024年经营得怎么样", client))
    assert out.route == "tools_blocked"
    assert "预算" in out.reply
    assert "未写入" in out.reply
    executed = [item["name"] for item in out.trace if not item.get("skipped") and item.get("name") != "number_check"]
    assert executed == []
