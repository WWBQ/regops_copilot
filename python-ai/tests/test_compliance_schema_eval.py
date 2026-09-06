"""W1-2 合规结论 Schema 校验评测的测试。

除了「当前 Schema 全过」这条回归门禁，更重要的是变异测试：
把 Schema 换成故意放宽/收紧的版本，确认 runner 能把问题标出来。
否则一份满分报告只能证明脚本会打印 100%，不能证明它有鉴别力。
"""

from typing import Literal

import pytest
from pydantic import BaseModel, Field

from app.eval import compliance_schema_runner as runner_mod
from app.eval.compliance_schema_runner import (
    render_markdown,
    run_compliance_schema_eval,
)
from app.eval.registry import GOLDEN_DIR

GOLDEN_PATH = GOLDEN_DIR / "compliance_schema_20.json"


@pytest.fixture
def report():
    return run_compliance_schema_eval(golden_path=GOLDEN_PATH)


def test_golden_set_shape():
    payload = runner_mod.load_golden(GOLDEN_PATH)
    items = payload["items"]
    ids = [item["id"] for item in items]

    assert len(items) == 20
    assert len(set(ids)) == 20
    assert sum(1 for i in items if i["category"] == "valid") == 10
    assert sum(1 for i in items if i["category"] == "invalid") == 10

    # 非法样例必须声明规则与期望报错，否则「拒对了但理由不对」无法被发现
    for item in items:
        assert item.get("rule"), f"{item['id']} 缺少 rule"
        if item["category"] == "invalid":
            assert item.get("expect_error_field") or item.get("expect_error_contains"), (
                f"{item['id']} 未声明期望报错"
            )


def test_current_schema_has_no_regression(report):
    summary = report["summary"]
    assert summary["total"] == 20
    assert summary["false_accept"] == 0, "存在非法结论被放行"
    assert summary["false_reject"] == 0, "存在合法结论被误拒"
    assert summary["accuracy"] == 1.0
    assert summary["rule_hit_rate"] == 1.0
    assert summary["strict_pass_rate"] == 1.0


def test_normalization_assertions_are_counted(report):
    # 只有显式声明 expect_normalized 的样例才应计入清洗统计
    summary = report["summary"]
    assert summary["normalization_checked"] == 2
    assert summary["normalization_passed"] == 2


def test_by_rule_covers_every_item(report):
    summary = report["summary"]
    assert sum(row["total"] for row in summary["by_rule"]) == 20
    assert {row["rule"] for row in summary["by_rule"]} == {
        item["rule"] for item in report["results"]
    }


def test_category_filter(report):
    invalid_only = run_compliance_schema_eval(golden_path=GOLDEN_PATH, category="invalid")
    assert invalid_only["summary"]["total"] == 10
    assert invalid_only["summary"]["valid_total"] == 0


class _PermissiveConclusion(BaseModel):
    """故意放宽：丢掉所有约束，只保留字段。"""

    conclusion: str = ""
    risk_level: str = "低"
    clause_refs: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class _OverStrictConclusion(BaseModel):
    """故意收紧：只接受低风险，合法的中/高风险会被误拒。"""

    conclusion: str = Field(..., min_length=1, max_length=500)
    risk_level: Literal["低"]
    clause_refs: list[str] = Field(..., min_length=1)
    evidence_quotes: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


def test_runner_detects_permissive_schema(monkeypatch):
    """放宽后的 Schema 应把非法样例几乎全部放行，误放行率必须飙升。"""
    monkeypatch.setattr(runner_mod, "ComplianceConclusion", _PermissiveConclusion)
    summary = run_compliance_schema_eval(golden_path=GOLDEN_PATH)["summary"]

    assert summary["false_accept"] >= 9
    assert summary["false_accept_rate"] >= 0.9
    assert summary["accuracy"] < 0.6
    assert summary["strict_pass_rate"] < 1.0


def test_runner_detects_overstrict_schema(monkeypatch):
    """收紧后的 Schema 应误拒合法的中/高风险结论。"""
    monkeypatch.setattr(runner_mod, "ComplianceConclusion", _OverStrictConclusion)
    summary = run_compliance_schema_eval(golden_path=GOLDEN_PATH)["summary"]

    assert summary["false_reject"] > 0
    assert summary["false_reject_rate"] > 0.0
    assert summary["strict_pass_rate"] < 1.0


def test_rule_match_flags_wrong_rejection_reason():
    """被拒但理由不是预期那条约束时，rule_matched 应为 False。"""
    item = {
        "id": "probe-001",
        "category": "invalid",
        "rule": "high_risk_confidence_cap",
        "expect_error_contains": "置信度不应超过 0.95",
        "payload": {
            # 真正触发的是 risk_level 枚举错误，而非跨字段的高风险置信度上限
            "conclusion": "测试",
            "risk_level": "未知",
            "clause_refs": ["A-1"],
            "confidence": 0.99,
        },
    }
    result = runner_mod.run_item(item)

    assert result["actual"] == "reject"
    assert result["decision_correct"] is True
    assert result["rule_matched"] is False
    assert result["passed"] is False


def test_render_markdown_contains_key_metrics(report):
    md = render_markdown(report)
    assert "# 合规结论 Schema 校验报告" in md
    assert "false_accept_rate" in md
    assert "无。" in md  # 当前无失败样例
