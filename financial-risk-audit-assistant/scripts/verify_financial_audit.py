"""金融初筛模式的离线冒烟验证：不调用模型或真实 RegOps 服务。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.backends.financial_read_only import FinancialReadOnlyBackend
from agent.core.runtime import _build_agent_user_content
from agent.core.task_intent import classify_task_kind, is_financial_audit_task, is_read_only_task
from agent.prompt import get_system_prompt
from agent.tools.financial_audit import _accepted_fact, lookup_financial_facts, search_report_evidence


def main() -> None:
    assert "金融风险审计助手" in get_system_prompt()
    assert "财务数值调用 `lookup_financial_facts`" in get_system_prompt()
    assert "开发实现" in get_system_prompt("coding")
    assert classify_task_kind("请对 000333 做 2024 年财务风险初筛") == "financial_audit"
    assert is_financial_audit_task("请修改金融风险审计助手的代码") is False
    assert is_read_only_task("financial_audit")

    content = _build_agent_user_content(
        repo_url=None,
        task_kind="financial_audit",
        prompt="请对 000333 做 2024 年财务风险初筛",
    )
    assert "不得执行本机命令" in content
    assert "Gitee 仓库地址" not in content

    with tempfile.TemporaryDirectory() as root:
        backend = FinancialReadOnlyBackend(root)
        assert backend.execute("echo should-not-run").exit_code == 126
        assert backend.write("/projects/test.txt", "x").error
        assert not (Path(root) / "projects" / "test.txt").exists()

    row = {
        "company_code": "000333", "concept": "revenue", "period": "2024-12-31",
        "scope": "consolidated", "status": "auto_accepted", "currency": "CNY",
        "value_yuan": "100.00", "doc_id": "000333_2024_report", "page_no": 86,
        "fact_key": "revenue-2024",
    }
    assert _accepted_fact([{**row, "period": "2024-09-30"}], company_code="000333", concept="revenue", year=2024)["outcome"] == "missing"
    assert _accepted_fact([{**row, "value_yuan": "NaN"}], company_code="000333", concept="revenue", year=2024)["outcome"] == "invalid_value"

    def fake_request(_method: str, path: str, **_kwargs: object) -> dict:
        if path == "/ops/quality/facts":
            return {"total": 1, "items": [row]}
        return {
            "rag_used": True, "reply": "候选摘要", "citations": [
                {"doc_id": "000333_2024_report", "page": 89, "snippet": "经营情况说明"},
                {"doc_id": "000333_2023_report", "page": 20, "snippet": "错误年份"},
            ],
        }

    with patch("agent.tools.financial_audit._request_json", side_effect=fake_request):
        facts = json.loads(lookup_financial_facts.invoke({
            "company_code": "000333", "concept": "revenue", "years": [2023, 2024],
        }))
        assert [item["outcome"] for item in facts["facts"]] == ["missing", "ok"]
        assert facts["facts"][1]["sources"][0]["page"] == 86

        evidence = json.loads(search_report_evidence.invoke({
            "company_code": "000333", "year": 2024, "question": "经营情况如何？",
        }))
        assert evidence["status"] == "ok"
        assert len(evidence["citations"]) == 1

    with patch("agent.tools.financial_audit._service_config", return_value=None):
        missing_config = json.loads(lookup_financial_facts.invoke({
            "company_code": "000333", "concept": "revenue", "years": [2024],
        }))
        assert missing_config["status"] == "unavailable"

    print("financial audit verification passed")


if __name__ == "__main__":
    main()
