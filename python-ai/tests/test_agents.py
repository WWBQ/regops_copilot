import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.checkpoint import checkpoint_expired, open_sqlite_checkpointer
from app.agents.graph import run_review_workflow
from app.agents.intent import checkpoint_command, tool_loop_reason, wants_review_graph, wants_tool_loop
from app.agents.tool_loop import run_tool_loop
from app.models.base import ChatResult, LLMClient, ToolCallRequest
from app.schemas.chat import Citation
from app.schemas.tools import ToolInvokeResponse


def test_plain_compare_stays_on_asknum():
    assert wants_review_graph("对比比亚迪和长城2024年营收") is False
    assert wants_review_graph("比亚迪2024年营业收入是多少") is False


def test_review_task_enters_graph():
    assert wants_review_graph("对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论") is True
    assert wants_review_graph("对比比亚迪和长城营收为什么差异这么大") is True


def test_tool_loop_is_opt_in():
    assert wants_tool_loop("比亚迪2024年营业收入是多少") is False
    assert wants_tool_loop("对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论") is False
    assert wants_tool_loop("你自己选工具：格力2024年有哪些可查指标，抽一条核对") is True
    assert wants_tool_loop("用工具帮我看看美的年报管理层怎么说分红") is True


def test_tool_loop_whitelist_excludes_write():
    from app.agents.tool_loop import ALLOWED_TOOLS

    assert "create_review_draft" not in ALLOWED_TOOLS
    assert "emit_conclusion" not in ALLOWED_TOOLS


def test_tool_loop_open_decisions():
    assert tool_loop_reason("格力2024年经营得怎么样") == "overview"
    assert tool_loop_reason("格力2024年有哪些可查指标") == "overview"
    assert tool_loop_reason("比亚迪研发投入多不多") == "unsupported_topic"
    assert tool_loop_reason("比亚迪2024年毛利率是多少") == "unsupported_topic"
    assert tool_loop_reason("格力2024年分红政策怎么说") == "unsupported_topic"
    assert tool_loop_reason("美的2024年营收到底能不能用") == "blocked_followup"
    assert tool_loop_reason("美的营收口径有什么问题") == "blocked_followup"


def test_tool_loop_does_not_steal_asknum_or_rag():
    assert wants_tool_loop("比亚迪今年数字多少") is False
    assert wants_tool_loop("查一下比亚迪财务数字") is False
    assert wants_tool_loop("营收多少") is False
    assert wants_tool_loop("比亚迪风险因素有哪些") is False
    assert wants_tool_loop("比亚迪2024年营收为什么增长") is False
    assert wants_tool_loop("美的2024年营收多少") is False


def _ok(name: str, result: dict) -> ToolInvokeResponse:
    return ToolInvokeResponse(name=name, ok=True, stop=False, result=result)


def _fail(name: str, message: str, result: dict | None = None, error_code: str = "missing") -> ToolInvokeResponse:
    return ToolInvokeResponse(
        name=name,
        ok=False,
        stop=True,
        result=result or {},
        error=message,
        error_code=error_code,  # type: ignore[arg-type]
    )


def _scripted_tools(**overrides):
    scope = _ok(
        "list_scope",
        {
            "ok": True,
            "companies": ["002594", "601633"],
            "items": [
                {
                    "company_code": "002594",
                    "year": 2024,
                    "scope": "consolidated",
                    "concepts": ["revenue", "net_profit"],
                },
                {
                    "company_code": "601633",
                    "year": 2024,
                    "scope": "consolidated",
                    "concepts": ["revenue", "net_profit"],
                },
            ],
        },
    )
    compare = _ok(
        "compare_peers",
        {
            "ok": True,
            "concept": "net_profit",
            "year": 2024,
            "scope": "consolidated",
            "lookups": [
                {
                    "ok": True,
                    "company_code": "002594",
                    "concept": "net_profit",
                    "year": 2024,
                    "scope": "consolidated",
                    "value_yuan": "41587940000",
                    "doc_id": "002594_2024",
                    "status": "auto_accepted",
                },
                {
                    "ok": True,
                    "company_code": "601633",
                    "concept": "net_profit",
                    "year": 2024,
                    "scope": "consolidated",
                    "value_yuan": "12660012515.78",
                    "doc_id": "601633_2024",
                    "status": "auto_accepted",
                },
            ],
        },
    )
    verify = _ok(
        "verify_number",
        {"ok": True, "stop": False, "verdict": "match", "lookup_outcome": "ok", "message": "match"},
    )
    rag = _ok(
        "rag_search",
        {
            "ok": True,
            "outcome": "ok",
            "citations": [
                {
                    "doc_id": "002594_2024",
                    "page": 20,
                    "snippet": "净利润变动主要来自销量与产品结构。",
                    "title": "比亚迪2024年年度报告",
                }
            ],
        },
    )
    conclude = _ok(
        "emit_conclusion",
        {
            "ok": True,
            "conclusion": {
                "conclusion": "ok",
                "risk_level": "低",
                "clause_refs": ["002594_2024#p20"],
                "confidence": 0.72,
            },
        },
    )
    draft = _ok(
        "create_review_draft",
        {
            "ok": True,
            "stop": False,
            "draft_id": "11111111-1111-1111-1111-111111111111",
            "status": "PENDING",
            "replayed": False,
            "message": "已写入 PENDING 审查工单草稿",
        },
    )
    table = {
        "list_scope": scope,
        "compare_peers": compare,
        "verify_number": verify,
        "rag_search": rag,
        "emit_conclusion": conclude,
        "create_review_draft": draft,
        **overrides,
    }

    def _call(name, arguments, request_id=None, **_kwargs):
        return table[name]

    return _call


def test_checkpoint_commands():
    assert checkpoint_command("确认") == "resume"
    assert checkpoint_command("继续") == "resume"
    assert checkpoint_command("取消") == "cancel"
    assert checkpoint_command("对比比亚迪和长城给出结论") is None
    assert checkpoint_expired("2000-01-01T00:00:00+00:00", ttl_hours=24) is True
    assert checkpoint_expired("2099-01-01T00:00:00+00:00", ttl_hours=24) is False


def test_review_graph_happy_path_is_replayable(monkeypatch):
    monkeypatch.setattr("app.agents.graph.call_tool", _scripted_tools())
    question = "对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论"

    def _finish():
        saver = InMemorySaver()
        paused = run_review_workflow(question, checkpointer=saver, dept="research")
        assert paused.route == "agent_paused"
        assert paused.pending_node == "conclude"
        return run_review_workflow(
            "确认",
            checkpointer=saver,
            thread_id=paused.thread_id,
            dept="research",
            action="resume",
        )

    first = _finish()
    second = _finish()
    path = [item["node"] for item in first.trace if item.get("node") != "number_check"]
    assert path == ["classify", "list_scope", "compare", "verify", "rag", "conclude"]
    assert path == [item["node"] for item in second.trace if item.get("node") != "number_check"]
    assert first.route == "agent"
    assert first.trace[-1]["name"] == "number_check"
    assert first.reply == second.reply
    assert "未手算" in first.reply
    assert "PENDING" in first.reply
    assert first.draft_id == "11111111-1111-1111-1111-111111111111"
    assert first.rag_used is True
    assert any(item.kind == "facts" for item in first.citations)
    assert any(item.page == 20 for item in first.citations)


def test_review_graph_pauses_before_conclusion(monkeypatch):
    base = _scripted_tools()
    calls: list[str] = []

    def tracked(name, arguments, request_id=None, **_kwargs):
        calls.append(name)
        return base(name, arguments, request_id)

    monkeypatch.setattr("app.agents.graph.call_tool", tracked)
    saver = InMemorySaver()
    paused = run_review_workflow(
        "对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论",
        checkpointer=saver,
        dept="research",
    )
    assert paused.route == "agent_paused"
    assert "待写入草稿预览" in paused.reply
    assert "影响范围" in paused.reply
    assert [item["node"] for item in paused.trace if item.get("node") != "number_check"] == [
        "classify",
        "list_scope",
        "compare",
        "verify",
        "rag",
        "checkpoint",
    ]
    assert "emit_conclusion" not in calls
    assert "create_review_draft" not in calls
    done = run_review_workflow(
        "确认",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="research",
        action="resume",
    )
    assert done.route == "agent"
    assert calls.count("compare_peers") == 1
    assert calls.count("rag_search") == 1
    assert calls.count("emit_conclusion") == 1
    assert calls.count("create_review_draft") == 1
    again = run_review_workflow(
        "确认",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="research",
        action="resume",
    )
    assert again.route == "agent"
    assert calls.count("emit_conclusion") == 1
    assert calls.count("create_review_draft") == 1


def test_review_graph_cancel_does_not_emit(monkeypatch):
    base = _scripted_tools()
    calls: list[str] = []

    def tracked(name, arguments, request_id=None, **_kwargs):
        calls.append(name)
        return base(name, arguments, request_id)

    monkeypatch.setattr("app.agents.graph.call_tool", tracked)
    saver = InMemorySaver()
    paused = run_review_workflow(
        "对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论",
        checkpointer=saver,
        dept="research",
    )
    cancelled = run_review_workflow(
        "取消",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="research",
        action="cancel",
    )
    assert cancelled.route == "agent_blocked"
    assert "emit_conclusion" not in calls
    assert "create_review_draft" not in calls
    assert "未写入" in cancelled.reply
    missing = run_review_workflow(
        "确认",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="research",
        action="resume",
    )
    assert missing.stop_reason == "checkpoint_missing"


def test_review_graph_rejects_other_dept(monkeypatch):
    monkeypatch.setattr("app.agents.graph.call_tool", _scripted_tools())
    saver = InMemorySaver()
    paused = run_review_workflow(
        "对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论",
        checkpointer=saver,
        dept="research",
    )
    out = run_review_workflow(
        "确认",
        checkpointer=saver,
        thread_id=paused.thread_id,
        dept="compliance",
        action="resume",
    )
    assert out.stop_reason == "checkpoint_forbidden"


def test_review_graph_survives_sqlite_reopen(monkeypatch, tmp_path):
    monkeypatch.setattr("app.agents.graph.call_tool", _scripted_tools())
    path = tmp_path / "review.sqlite"
    saver = open_sqlite_checkpointer(path)
    paused = run_review_workflow(
        "对比比亚迪和长城2024年净利润，并结合管理层讨论给出结论",
        checkpointer=saver,
        dept="research",
    )
    assert paused.route == "agent_paused"
    thread_id = paused.thread_id
    saver.conn.close()
    restored = open_sqlite_checkpointer(path)
    done = run_review_workflow(
        "确认",
        checkpointer=restored,
        thread_id=thread_id,
        dept="research",
        action="resume",
    )
    assert done.route == "agent"
    assert "conclude" in [item["node"] for item in done.trace]
    restored.conn.close()


def test_review_graph_stops_when_compare_missing(monkeypatch):
    monkeypatch.setattr(
        "app.agents.graph.call_tool",
        _scripted_tools(
            compare_peers=_fail("compare_peers", "至少一家无数据", {"ok": False, "lookups": []}),
        ),
    )
    out = run_review_workflow(
        "对比比亚迪和长城2024年净利润并给出结论",
        checkpointer=InMemorySaver(),
    )
    assert out.route == "agent_blocked"
    assert "conclude" not in [item["node"] for item in out.trace]
    assert "stop" in [item["node"] for item in out.trace]
    assert "不" in out.reply or "停止" in out.reply or "无数据" in out.reply


def test_review_graph_lists_scope_before_missing_concept(monkeypatch):
    monkeypatch.setattr("app.agents.graph.call_tool", _scripted_tools())
    out = run_review_workflow("对比比亚迪和长城给出合规结论", checkpointer=InMemorySaver())
    assert out.route == "agent_blocked"
    assert [item["node"] for item in out.trace][:2] == ["classify", "list_scope"]
    assert "指标" in out.reply


class _ScriptedLLM(LLMClient):
    def __init__(self, rounds: list[ChatResult]) -> None:
        self._rounds = list(rounds)

    async def chat(self, messages, *, temperature=0.1) -> str:
        result = await self.chat_with_usage(messages, temperature=temperature)
        return result.content

    async def chat_with_usage(self, messages, *, temperature=0.1, tools=None) -> ChatResult:
        if not self._rounds:
            return ChatResult(content="没有更多步骤")
        return self._rounds.pop(0)


def test_tool_loop_lets_model_pick_tools(monkeypatch):
    monkeypatch.setattr(
        "app.agents.tool_loop.invoke_tool",
        lambda name, arguments=None, context=None: _ok(
            name,
            {
                "ok": True,
                "stop": False,
                "companies": ["000651"],
                "items": [{"company_code": "000651", "year": 2024, "scope": "consolidated", "concepts": ["revenue"]}],
                "outcome": "ok",
                "company_code": "000651",
                "concept": "revenue",
                "year": 2024,
                "scope": "consolidated",
                "value_yuan": "1",
                "doc_id": "000651_2024",
                "status": "auto_accepted",
                "citations": [
                    {"doc_id": "000651_2024", "page": 12, "snippet": "管理层讨论分红", "title": "格力2024年报"}
                ],
                "message": "ok",
            },
        ),
    )
    client = _ScriptedLLM(
        [
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(id="c1", name="list_scope", arguments={"company_code": "000651", "year": 2024})
                ],
            ),
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c2",
                        name="lookup_metric",
                        arguments={"company_code": "000651", "concept": "revenue", "year": 2024},
                    )
                ],
            ),
            ChatResult(content="格力 2024 营收来自工具返回，未手算。"),
        ]
    )
    out = asyncio.run(run_tool_loop("你自己选工具：格力2024年有哪些可查指标", client))
    assert out.route == "tools"
    assert [item["name"] for item in out.trace if item["name"] != "number_check"] == ["list_scope", "lookup_metric"]
    assert out.trace[-1]["name"] == "number_check"
    assert out.trace[-1]["ok"] is True
    assert "【工具自选】" in out.reply
    assert "list_scope → lookup_metric" in out.reply
    assert "未手算" in out.reply


def test_tool_loop_injects_citation_marks(monkeypatch):
    monkeypatch.setattr(
        "app.agents.tool_loop.invoke_tool",
        lambda name, arguments=None, context=None: _ok(
            name,
            {
                "ok": True,
                "stop": False,
                "company_code": "000651",
                "concept": "net_profit",
                "year": 2024,
                "value_yuan": "32371069287.35",
                "doc_id": "000651_2024",
                "status": "auto_accepted",
                "message": "ok",
                "citations": [
                    {
                        "doc_id": "000651_2024",
                        "page": 13,
                        "snippet": "营业总收入1,900.38亿元",
                        "title": "格力2024年报",
                    }
                ],
            },
        ),
    )
    client = _ScriptedLLM(
        [
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="lookup_metric",
                        arguments={"company_code": "000651", "concept": "net_profit", "year": 2024},
                    )
                ],
            ),
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c2",
                        name="rag_search",
                        arguments={"question": "格力2024经营情况"},
                    )
                ],
            ),
            ChatResult(
                content="净利润：323.71 亿元。年报叙述提到营业总收入（doc_id: 000651_2024，第13页）。未手算。"
            ),
        ]
    )
    out = asyncio.run(run_tool_loop("格力2024年经营得怎么样", client))
    assert "[1]" in out.reply
    assert "[2]" in out.reply
    assert "doc_id:" not in out.reply
    assert "出处" not in out.reply
    assert len(out.citations) == 2
    assert out.citations[0].kind == "facts"
    assert out.citations[1].page == 13


def test_inject_marks_matches_yi_thousands_and_rag_amount():
    from app.agents.tool_loop import _bind_citations

    cites = [
        Citation(
            doc_id="000651_2024",
            page=1,
            snippet="格力电器 资产总计 368031704522.86",
            href="/quality/facts?concept=total_assets",
            kind="facts",
        ),
        Citation(
            doc_id="000651_2024",
            page=99,
            snippet="无关片段",
            title="格力电器2024年年度报告",
            kind="document",
        ),
        Citation(
            doc_id="000651_2024",
            page=13,
            snippet="营业总收入1,900.38亿元",
            title="格力电器2024年年度报告",
            kind="document",
        ),
    ]
    text = (
        "| **资产总计** | 3,680.32 亿元（368,031,704,522.86 元） |\n"
        "营业总收入 1,900.38 亿元，非已核对数字。"
    )
    out, bound = _bind_citations(text, cites)
    assert "3,680.32 亿元[1]" in out or "368,031,704,522.86[1]" in out
    assert "1,900.38[2]" in out
    assert "出处" not in out
    assert [item.page for item in bound] == [1, 13]
    assert len(bound) == 2


def test_tool_loop_caps_lookup_metric(monkeypatch):
    calls: list[str] = []

    def fake_invoke(name, arguments=None, context=None):
        calls.append(name)
        if name == "rag_search":
            return _ok(
                name,
                {
                    "ok": True,
                    "stop": False,
                    "message": "ok",
                    "citations": [
                        {
                            "doc_id": "000651_2024",
                            "page": 13,
                            "snippet": "管理层讨论",
                            "title": "格力2024年报",
                        }
                    ],
                },
            )
        return _ok(name, {"ok": True, "stop": False, "message": "ok", "company_code": "000651"})

    monkeypatch.setattr("app.agents.tool_loop.invoke_tool", fake_invoke)
    lookups = [
        ToolCallRequest(
            id=f"l{i}",
            name="lookup_metric",
            arguments={"company_code": "000651", "concept": "net_profit", "year": 2024},
        )
        for i in range(8)
    ]
    client = _ScriptedLLM(
        [
            ChatResult(content="", tool_calls=lookups),
            ChatResult(content="只根据已查到的三条作答，未手算。"),
            ChatResult(content="综合年报后作答，未手算。"),
        ]
    )
    out = asyncio.run(run_tool_loop("格力2024年经营得怎么样", client))
    assert calls.count("lookup_metric") == 1
    assert "rag_search" in calls
    executed = [item["name"] for item in out.trace if not item.get("skipped") and item["name"] != "number_check"]
    skipped = [item for item in out.trace if item.get("skipped")]
    assert executed == ["lookup_metric", "rag_search"]
    assert len(skipped) == 7
    assert "lookup_metric → rag_search" in out.reply
    assert "综合年报" in out.reply


def test_tool_loop_scope_question_does_not_force_rag(monkeypatch):
    calls: list[str] = []

    def fake_invoke(name, arguments=None, context=None):
        calls.append(name)
        return _ok(name, {"ok": True, "stop": False, "message": "ok", "companies": ["000651"]})

    monkeypatch.setattr("app.agents.tool_loop.invoke_tool", fake_invoke)
    client = _ScriptedLLM(
        [
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(id="c1", name="list_scope", arguments={"company_code": "000651", "year": 2024})
                ],
            ),
            ChatResult(content="可查指标见 list_scope，未手算。"),
        ]
    )
    out = asyncio.run(run_tool_loop("格力2024年有哪些可查指标", client))
    assert calls == ["list_scope"]
    assert "rag_search" not in out.reply
    assert "未手算" in out.reply


def test_tool_loop_batches_lookup_metric(monkeypatch):
    calls: list[str] = []

    def fake_invoke(name, arguments=None, context=None):
        calls.append(name)
        if name == "lookup_metric":
            return _ok(
                name,
                {
                    "ok": True,
                    "lookups": [
                        {
                            "ok": True,
                            "company_code": "002594",
                            "concept": "revenue",
                            "year": 2024,
                            "value_yuan": "777102455000",
                            "status": "auto_accepted",
                            "doc_id": "002594_2024",
                        },
                        {
                            "ok": True,
                            "company_code": "002594",
                            "concept": "net_profit_attributable",
                            "year": 2024,
                            "value_yuan": "40254346000",
                            "status": "auto_accepted",
                            "doc_id": "002594_2024",
                        },
                    ],
                },
            )
        if name == "rag_search":
            return _ok(
                name,
                {
                    "ok": True,
                    "citations": [
                        {
                            "doc_id": "002594_2024",
                            "page": 13,
                            "snippet": "营业总收入",
                            "title": "比亚迪2024年报",
                        }
                    ],
                },
            )
        return _ok(name, {"ok": True, "message": "ok"})

    monkeypatch.setattr("app.agents.tool_loop.invoke_tool", fake_invoke)
    client = _ScriptedLLM(
        [
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="b1",
                        name="lookup_metric",
                        arguments={
                            "company_code": "002594",
                            "year": 2024,
                            "concepts": ["revenue", "net_profit_attributable"],
                        },
                    )
                ],
            ),
            ChatResult(content="营业收入 777,102,455,000 元，归母净利润 40,254,346,000 元。未手算。"),
            ChatResult(content="营业收入 777,102,455,000 元，归母净利润 40,254,346,000 元。年报第13页概述。未手算。"),
        ]
    )
    out = asyncio.run(run_tool_loop("比亚迪2024年经营得怎么样", client))
    assert calls == ["lookup_metric", "rag_search"]
    assert "lookup_metric → rag_search" in out.reply
    assert "[1]" in out.reply
    assert len(out.citations) >= 1


def test_tool_loop_blocks_unbacked_amount(monkeypatch):
    monkeypatch.setattr(
        "app.agents.tool_loop.invoke_tool",
        lambda name, arguments=None, context=None: _ok(
            name,
            {
                "ok": True,
                "company_code": "002594",
                "concept": "net_profit",
                "year": 2024,
                "value_yuan": "41587940000",
                "doc_id": "002594_2024",
                "status": "auto_accepted",
                "message": "ok",
            },
        ),
    )
    client = _ScriptedLLM(
        [
            ChatResult(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="lookup_metric",
                        arguments={"company_code": "002594", "concept": "net_profit", "year": 2024},
                    )
                ],
            ),
            ChatResult(content="净利润约 542 亿元，未手算。"),
        ]
    )
    out = asyncio.run(run_tool_loop("你自己选工具：比亚迪净利润核对", client))
    assert out.route == "tools_blocked"
    assert "【数字校验拦截】" in out.reply
    assert "〔无证据〕" in out.reply
    assert out.trace[-1]["name"] == "number_check"
    assert out.trace[-1]["ok"] is False
