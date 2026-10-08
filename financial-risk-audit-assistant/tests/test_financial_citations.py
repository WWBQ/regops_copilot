import json
import unittest

from langchain_core.messages import HumanMessage, ToolMessage

from agent.financial.citations import (
    ToolCitationIndexer,
    citations_from_latest_turn,
    citations_from_messages,
    max_citation_id_from_messages,
)
from agent.financial.risk_result import parse_risk_audit_output


def _evidence_message(citation_id: int, doc_id: str) -> ToolMessage:
    payload = {
        "citations": [{
            "citation_id": citation_id,
            "doc_id": doc_id,
            "page": 3,
            "snippet": "风险证据",
        }],
    }
    return ToolMessage(content=json.dumps(payload), tool_call_id=f"call-{doc_id}")


class FinancialCitationTest(unittest.TestCase):
    def test_indexer_can_produce_id_34_with_only_one_visible_citation(self):
        candidates = [
            {"doc_id": "", "page": None, "snippet": f"候选 {number}"}
            for number in range(1, 34)
        ]
        candidates.append({"doc_id": "report-34", "page": 3, "snippet": "有效证据"})
        indexed = ToolCitationIndexer().annotate(
            "search_report_evidence", {"citations": candidates}
        )
        message = ToolMessage(
            content=json.dumps(indexed), tool_call_id="call-sparse-candidates"
        )
        citations = citations_from_messages([message])
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["citation_id"], 34)

    def test_sparse_ids_are_not_array_positions(self):
        citations = citations_from_messages([
            _evidence_message(7, "report-7"),
            _evidence_message(34, "report-34"),
        ])
        self.assertEqual([item["citation_id"] for item in citations], [7, 34])
        self.assertEqual(citations[1]["doc_id"], "report-34")

    def test_latest_turn_does_not_reuse_same_number_from_previous_turn(self):
        messages = [
            HumanMessage(content="上一轮"),
            _evidence_message(1, "old-report"),
            HumanMessage(content="这一轮"),
            _evidence_message(1, "new-report"),
        ]
        self.assertEqual(citations_from_messages(messages)[0]["doc_id"], "old-report")
        self.assertEqual(citations_from_latest_turn(messages)[0]["doc_id"], "new-report")

    def test_followup_allocates_new_ids_after_prior_tool_results(self):
        prior = [
            _evidence_message(1, "old-fact"),
            _evidence_message(34, "old-report"),
        ]
        indexer = ToolCitationIndexer(start_after=max_citation_id_from_messages(prior))
        current = indexer.annotate("search_report_evidence", {
            "citations": [{"doc_id": "new-report", "page": 241, "snippet": "股本"}],
        })
        self.assertEqual(current["citations"][0]["citation_id"], 35)
        current_message = ToolMessage(content=json.dumps(current), tool_call_id="new-call")
        available = {item["citation_id"] for item in citations_from_latest_turn([
            HumanMessage(content="上一轮"), *prior,
            HumanMessage(content="这一轮"), current_message,
        ])}
        _markdown, _result, error = parse_risk_audit_output(
            "归母净利润 337.45 亿元 [1]", available_citation_ids=available,
        )
        self.assertEqual(error, "unknown_body_citation_ids: [1]")

    def test_parser_accepts_valid_sparse_id_and_rejects_unknown_id(self):
        payload = {
            "company_code": "000333",
            "company_name": "美的集团",
            "year": 2024,
            "status": "completed",
            "findings": [{
                "risk_type": "盈利质量",
                "severity": "medium",
                "conclusion": "需要人工核查",
                "evidence_ids": [34],
                "uncertainty": "缺少底稿",
                "review_question": "是否有减值测试？",
            }],
            "summary": "发现待核查线索",
        }
        text = "报告引用 [34]\n```risk_audit_result\n" + json.dumps(payload) + "\n```"
        _markdown, result, error = parse_risk_audit_output(
            text, available_citation_ids={7, 9, 34},
        )
        self.assertIsNone(error)
        self.assertEqual(result.findings[0].evidence_ids, [34])
        blocked_markdown, result, error = parse_risk_audit_output(
            text.replace("报告引用 [34]", "报告引用"),
            available_citation_ids={7, 9, 11},
        )
        self.assertIsNone(result)
        self.assertEqual(error, "unknown_citation_ids: [34]")
        self.assertIn("已拦截", blocked_markdown)

    def test_parser_blocks_unverified_markdown_citation(self):
        text = "初筛发现线索 [18]。"
        markdown, result, error = parse_risk_audit_output(
            text, available_citation_ids={7, 9, 34},
        )
        self.assertIsNone(result)
        self.assertEqual(error, "unknown_body_citation_ids: [18]")
        self.assertNotIn("[18]", markdown)
        self.assertIn("已拦截", markdown)


if __name__ == "__main__":
    unittest.main()
