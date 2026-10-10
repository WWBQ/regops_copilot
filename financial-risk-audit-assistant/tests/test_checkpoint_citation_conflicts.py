import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.core.checkpoint_history import visible_checkpoint_messages


class CheckpointCitationConflictTest(unittest.TestCase):
    def test_short_final_answers_survive_refresh_and_repeated_questions(self):
        history = [
            HumanMessage(content="你好"),
            AIMessage(content="我先检查一下。"),
            AIMessage(content="你好！有什么可以帮你？"),
            HumanMessage(content="你好"),
            AIMessage(content="正在调用工具", tool_calls=[{
                "name": "read_file", "args": {"path": "main.py"}, "id": "call-1",
            }]),
            ToolMessage(content="ok", tool_call_id="call-1"),
            AIMessage(content="你好！有什么可以帮你？"),
        ]
        with patch("agent.core.checkpoint_history._delta_messages_from_checkpoint", return_value=history):
            visible = visible_checkpoint_messages("thread-1")

        self.assertEqual([item["author"] for item in visible], ["user", "agent", "user", "agent"])
        self.assertEqual([item["content"] for item in visible if item["author"] == "agent"], [
            "你好！有什么可以帮你？", "你好！有什么可以帮你？",
        ])
        self.assertEqual(len({item["message_id"] for item in visible}), len(visible))

    def test_tool_call_without_final_answer_is_not_shown_as_reply(self):
        history = [
            HumanMessage(content="检查代码"),
            AIMessage(content="准备读取文件", tool_calls=[{
                "name": "read_file", "args": {"path": "main.py"}, "id": "call-1",
            }]),
            ToolMessage(content="ok", tool_call_id="call-1"),
        ]
        with patch("agent.core.checkpoint_history._delta_messages_from_checkpoint", return_value=history):
            visible = visible_checkpoint_messages("thread-1")
        self.assertEqual([item["author"] for item in visible], ["user"])

    def test_old_answer_keeps_source_but_reused_id_is_disabled_in_followup(self):
        fact = ToolMessage(
            content=json.dumps({
                "company_code": "000333", "concept": "net_profit",
                "facts": [{"year": 2023, "outcome": "ok", "value_yuan": "33745352000", "citation_id": 1}],
            }),
            tool_call_id="fact-call", name="lookup_financial_facts",
        )
        document = ToolMessage(
            content=json.dumps({"citations": [{
                "doc_id": "000333_2024", "page": 241, "snippet": "股本变动", "citation_id": 1,
            }]}),
            tool_call_id="document-call", name="search_report_evidence",
        )
        history = [
            HumanMessage(content="第一轮"), fact,
            AIMessage(content="# 财务事实\n净利润 337.45 亿元 [1]"),
            HumanMessage(content="第二轮"), document,
            AIMessage(content="# 风险报告\n净利润 337.45 亿元 [1]"),
        ]
        with patch("agent.core.checkpoint_history._delta_messages_from_checkpoint", return_value=history):
            visible = visible_checkpoint_messages("thread-1")

        first, second = [item for item in visible if item["author"] == "agent"]
        self.assertEqual(first["citations"][0]["kind"], "facts")
        self.assertEqual(second["citations"], [])
        self.assertEqual(second["citation_conflicts"], [1])


if __name__ == "__main__":
    unittest.main()
