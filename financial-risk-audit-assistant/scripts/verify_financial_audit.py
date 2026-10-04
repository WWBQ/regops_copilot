"""金融初筛模式的离线冒烟验证：不调用模型或真实 RegOps 服务。"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi.responses import PlainTextResponse
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import app as agent_app
from agent.api import risk_agent
from agent.core import runtime
from agent.core import model as agent_model
from agent.core.runtime import _build_agent_user_content
from agent.core.task_intent import classify_task_kind, is_financial_audit_task, is_read_only_task
from agent.prompt import get_system_prompt
from agent.financial import TOOLS_UNAVAILABLE_MESSAGE
from agent.financial.citations import ToolCitationIndexer, citations_from_messages
from agent.server import get_agent
from agent import server as agent_server
from agent.mcp import financial_client
from agent.store.sqlite_store import LocalSqliteStore
from agent.tools.gitee_tools import _resolve_explicit_repo


def main() -> None:
    assert "金融风险审计助手" in get_system_prompt()
    assert "lookup_financial_facts" in get_system_prompt()
    assert "开发实现" in get_system_prompt("coding")
    assert classify_task_kind("请对 000333 做 2024 年财务风险初筛") == "financial_audit"
    assert is_financial_audit_task("请修改金融风险审计助手的代码") is False
    assert is_read_only_task("financial_audit")

    # 同一轮工具调用共享编号：F10 事实链接事实库，PDF 证据链接年报页。
    citation_indexer = ToolCitationIndexer()
    facts_payload = citation_indexer.annotate(
        "lookup_financial_facts",
        {
            "status": "ok", "company_code": "002594", "concept": "revenue",
            "facts": [{
                "year": 2024, "outcome": "ok", "value_yuan": "777102470000.00",
                "scope": "consolidated", "sources": [{"doc_id": "002594_2024"}],
            }],
        },
    )
    evidence_payload = citation_indexer.annotate(
        "search_report_evidence",
        {
            "status": "ok", "citations": [
                {"doc_id": "002594_2024", "page": 88, "snippet": "营业收入同比增长。"},
            ],
        },
    )
    assert facts_payload["facts"][0]["citation_id"] == 1
    assert evidence_payload["citations"][0]["citation_id"] == 2
    citations = citations_from_messages([
        ToolMessage(content=json.dumps(facts_payload, ensure_ascii=False), tool_call_id="facts"),
        ToolMessage(content=json.dumps(evidence_payload, ensure_ascii=False), tool_call_id="evidence"),
    ])
    assert citations[0]["kind"] == "facts"
    assert citations[0]["href"].startswith("/quality/facts?")
    assert citations[1]["kind"] == "document"
    assert citations[1]["page"] == 88
    model_env = {
        "DEEPSEEK_API_KEY": "test-deepseek-key",
        "QWEN_API_KEY": "test-qwen-key",
        "MAIN_MODEL": "deepseek-v4-pro",
    }
    with patch.object(agent_model, "get_env", side_effect=lambda key, default="": model_env.get(key, default)):
        models = agent_model.available_agent_models()
        assert list(models) == ["deepseek-flash", "deepseek-v4-pro", "qwen3.8-max", "qwen3.8-flash", "qwen3.7-plus"]
        assert agent_model.default_agent_model_id(models) == "deepseek-v4-pro"
        with patch.object(agent_model, "init_chat_model", return_value=object()) as init:
            agent_model.make_main_model("qwen3.8-max")
            assert init.call_args.kwargs["model"] == "qwen3.8-max"
            assert init.call_args.kwargs["api_key"] == "test-qwen-key"
            assert "extra_body" not in init.call_args.kwargs
            agent_model.make_main_model("deepseek-flash")
            assert init.call_args.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
        try:
            agent_model.require_agent_model_id("unknown-model")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown model must be rejected")
    with patch.object(runtime, "get_agent", return_value=object()) as build_agent:
        runtime._build_agent_for_runtime(
            thread_id="model-selection-test", task_kind="financial_audit", model_id="qwen3.8-max",
        )
        assert build_agent.call_args.args[0]["configurable"]["model_id"] == "qwen3.8-max"
    repo, missing_repo_error = _resolve_explicit_repo("")
    assert repo is None and "没有仓库地址" in (missing_repo_error or "")

    # RegOps 页面入口不受用户文字影响，即使要求写代码也只能走只读金融模式。
    with tempfile.TemporaryDirectory() as root:
        store = LocalSqliteStore(Path(root) / "store.sqlite")
        try:
            with (
                patch.object(runtime, "get_store", return_value=store),
                patch.object(runtime, "record_event"),
                patch.object(runtime, "classify_task_kind", side_effect=AssertionError("must not classify")),
                patch.object(runtime, "is_workspace_listing_task", side_effect=AssertionError("must not list workspace")),
                patch.object(runtime, "is_pull_only_task", side_effect=AssertionError("must not pull")),
                patch.object(runtime, "_build_agent_for_runtime", return_value=object()) as build,
                patch.object(runtime, "run_agent_with_event_stream", return_value={"messages": []}) as stream,
            ):
                result = runtime.run_agent_task(
                    repo_url=None,
                    prompt="请修改仓库代码并提交",
                    thread_id="regops-read-only-test",
                    forced_financial_audit=True,
                )
                assert result["status"] == "completed"
                assert result["final_answer"] == ""
                assert build.call_args.kwargs["task_kind"] == "financial_audit"
                assert stream.call_args.kwargs["task_kind"] == "financial_audit"
        finally:
            store.close()

    content = _build_agent_user_content(
        repo_url=None,
        task_kind="financial_audit",
        prompt="请对 000333 做 2024 年财务风险初筛",
    )
    assert "不得执行本机命令" in content
    assert "Gitee 仓库地址" not in content

    financial_config = {"configurable": {
        "thread_id": "financial-no-tools-test", "task_kind": "financial_audit",
        "__is_for_execution__": True,
    }}
    with patch.object(agent_server, "load_financial_tools", side_effect=RuntimeError(TOOLS_UNAVAILABLE_MESSAGE)):
        try:
            get_agent(financial_config)
        except RuntimeError as exc:
            assert str(exc) == TOOLS_UNAVAILABLE_MESSAGE
        else:
            raise AssertionError("MCP 服务不可用时不能创建金融 Agent")

    class ExtraToolClient:
        def __init__(self, _connections):
            pass

        async def get_tools(self):
            return [SimpleNamespace(name=name) for name in (
                "lookup_financial_facts", "search_report_evidence", "unexpected_write_tool",
            )]

    with (
        patch.object(financial_client, "_mcp_connection", return_value={}),
        patch.object(financial_client, "MultiServerMCPClient", ExtraToolClient),
    ):
        assert {item.name for item in asyncio.run(financial_client._discover_tools())} == {
            "lookup_financial_facts", "search_report_evidence",
        }

    class FakeGraph:
        def with_config(self, _config):
            return self

    financial_tools = [SimpleNamespace(name="lookup_financial_facts"), SimpleNamespace(name="search_report_evidence")]
    with (
        patch.object(agent_server, "load_financial_tools", return_value=financial_tools),
        patch.object(agent_server, "make_main_model", return_value=object()),
        patch.object(agent_server, "create_agent", return_value=FakeGraph()) as create_financial,
        patch.object(agent_server, "ensure_backend_for_thread", side_effect=AssertionError("financial mode must not create shell backend")),
    ):
        get_agent(financial_config)
        assert create_financial.call_args.kwargs["tools"] == financial_tools
        assert "backend" not in create_financial.call_args.kwargs
        assert "subagents" not in create_financial.call_args.kwargs

    # 不调用外部模型/服务，真实跑一轮 LangChain Agent 图：模型请求 MCP 工具，
    # 图执行工具，再由模型基于结果给出最终回复。这个测试不能只 mock 构图。
    async def mock_lookup(company_code: str, concept: str, years: list[int]) -> list[dict]:
        return [{"type": "text", "text": json.dumps({
            "status": "ok", "company_code": company_code, "concept": concept, "years": years,
        })}]

    async def mock_search(company_code: str, year: int, question: str) -> list[dict]:
        return [{"type": "text", "text": '{"status":"insufficient_evidence"}'}]

    lookup_financial_facts = financial_client._sync_tool(StructuredTool.from_function(
        coroutine=mock_lookup, name="lookup_financial_facts", description="离线财务事实查询测试工具。",
    ))
    search_report_evidence = financial_client._sync_tool(StructuredTool.from_function(
        coroutine=mock_search, name="search_report_evidence", description="离线年报证据检索测试工具。",
    ))

    class ToolCallingFakeModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            assert {item.name for item in tools} == {"lookup_financial_facts", "search_report_evidence"}
            return self

    fake_model = ToolCallingFakeModel(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "lookup_financial_facts",
            "args": {"company_code": "000333", "concept": "revenue", "years": [2024]},
            "id": "offline-financial-call",
        }]),
        AIMessage(content="已获得带来源的财务事实，仍需人工核查。"),
    ])
    with (
        patch.object(agent_server, "load_financial_tools", return_value=[lookup_financial_facts, search_report_evidence]),
        patch.object(agent_server, "make_main_model", return_value=fake_model),
        patch("agent.core.graph.get_checkpointer", return_value=MemorySaver()),
        patch.object(agent_server, "ensure_backend_for_thread", side_effect=AssertionError("financial mode must not create shell backend")),
    ):
        graph = get_agent(financial_config)
        result = graph.invoke({"messages": [HumanMessage(content="检查美的营收")]})
        assert any(isinstance(message, ToolMessage) and "000333" in message.content for message in result["messages"])
        assert result["messages"][-1].content == "已获得带来源的财务事实，仍需人工核查。"
        fake_model.i = 0
        stream_config = {"configurable": {
            "thread_id": "financial-stream-test", "task_kind": "financial_audit",
            "__is_for_execution__": True,
        }}
        stream_graph = get_agent(stream_config)
        stream = stream_graph.stream_events(
            {"messages": [{"role": "user", "content": "检查美的营收"}]},
            version="v3",
            config={"configurable": {"thread_id": "financial-stream-test"}},
        )
        list(stream)
        assert stream.output["messages"][-1].content == "已获得带来源的财务事实，仍需人工核查。"

    # 页面入口必须在创建会话或调用模型前明确拒绝金融初筛。
    fake_thread = {"thread_id": "test-thread", "title": "测试初筛", "latest_run_status": "completed"}
    with (
        patch.object(risk_agent, "load_financial_tools", side_effect=RuntimeError(TOOLS_UNAVAILABLE_MESSAGE)),
        patch.object(risk_agent, "initialize_task_record") as initialize,
        patch.object(risk_agent, "get_task", return_value=fake_thread),
        patch.object(risk_agent, "visible_checkpoint_messages", return_value=[]) as checkpoint_messages,
        patch.object(risk_agent, "run_agent_task", return_value={"final_answer": "需要人工核查。"}) as run,
        patch.object(risk_agent, "require_agent_model_id") as require_model,
    ):
        assert "messages" not in risk_agent._thread_meta_payload(fake_thread)
        checkpoint_messages.assert_not_called()
        thread_payload = risk_agent._thread_payload({
            **fake_thread, "repo_owner": "old-owner", "repo_name": "old-repo",
        })
        assert "repo" not in thread_payload and "repoFullName" not in thread_payload
        response = TestClient(agent_app.app).post(
            "/regops/agent/threads/stream-message",
            headers={
                "X-Regops-Service-Token": risk_agent.get_env("REGOPS_SERVICE_TOKEN"),
                "X-Regops-User": "00000000-0000-0000-0000-000000000001",
            },
            json={"content": "检查 000333", "model_id": "qwen3.8-max", "repo": "https://gitee.com/example-org/sample_repo"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == TOOLS_UNAVAILABLE_MESSAGE
        initialize.assert_not_called()
        run.assert_not_called()
        require_model.assert_not_called()

        headers = {
            "X-Regops-Service-Token": risk_agent.get_env("REGOPS_SERVICE_TOKEN"),
            "X-Regops-User": "00000000-0000-0000-0000-000000000001",
        }
        owned_thread = "00000000-0000-0000-0000-000000000001_00000000-0000-0000-0000-000000000003"
        existing = TestClient(agent_app.app).post(
            f"/regops/agent/threads/{owned_thread}/stream-message",
            headers=headers,
            json={"content": "检查 000333"},
        )
        assert existing.status_code == 503
        assert existing.json()["detail"] == TOOLS_UNAVAILABLE_MESSAGE

        foreign_thread = "00000000-0000-0000-0000-000000000002_00000000-0000-0000-0000-000000000003"
        foreign = TestClient(agent_app.app).post(
            f"/regops/agent/threads/{foreign_thread}/stream-message",
            headers=headers,
            json={"content": "检查 000333"},
        )
        assert foreign.status_code == 404
        run.assert_not_called()

    # MCP 预检通过后，页面入口必须进入流式处理，而不是继续固定返回 503。
    with (
        patch.object(risk_agent, "load_financial_tools", return_value=financial_tools) as load,
        patch.object(risk_agent, "_post_streaming_response", return_value=PlainTextResponse("ready")) as start,
    ):
        ready = TestClient(agent_app.app).post(
            "/regops/agent/threads/stream-message",
            headers=headers,
            json={"content": "检查 000333 的 2024 年财报"},
        )
        assert ready.status_code == 200
        assert ready.text == "ready"
        load.assert_called_once()
        assert start.call_args.kwargs["content"] == "检查 000333 的 2024 年财报"

        # 继续已有会话时也必须在线程池中完成 MCP 预检，不能在 async 路由中
        # 直接进入使用 asyncio.run 的同步工具发现入口。
        with patch.object(risk_agent, "get_task", return_value={"thread_id": owned_thread}):
            continued = TestClient(agent_app.app).post(
                f"/regops/agent/threads/{owned_thread}/stream-message",
                headers=headers,
                json={"content": "继续核查营业收入", "model_id": "qwen3.8-max"},
            )
        assert continued.status_code == 200
        assert continued.text == "ready"
        assert start.call_args.kwargs["thread_id"] == owned_thread

    print("financial audit verification passed")


if __name__ == "__main__":
    main()
