import pytest
from pydantic import ValidationError

from app.schemas.compliance import ComplianceConclusion


def test_valid_compliance_conclusion():
    item = ComplianceConclusion(
        conclusion="客户交易行为需进一步审查",
        risk_level="中",
        clause_refs=["AML-12-3"],
        evidence_quotes=["第 3 章第 2 节"],
        confidence=0.82,
    )
    assert item.risk_level == "中"


@pytest.mark.parametrize("risk_level", ["低", "中", "高"])
def test_all_risk_levels_accepted(risk_level):
    item = ComplianceConclusion(
        conclusion="结论正文",
        risk_level=risk_level,
        clause_refs=["AML-12-3"],
        confidence=0.5,
    )
    assert item.risk_level == risk_level


@pytest.mark.parametrize(
    ("risk_level", "confidence"),
    [
        ("低", 0.0),  # 下界
        ("低", 1.0),  # 上界（非高风险可取满）
        ("高", 0.95),  # 高风险上限恰好，规则为「不应超过」故放行
    ],
)
def test_confidence_boundaries_accepted(risk_level, confidence):
    item = ComplianceConclusion(
        conclusion="结论正文",
        risk_level=risk_level,
        clause_refs=["AML-12-3"],
        confidence=confidence,
    )
    assert item.confidence == confidence


def test_evidence_quotes_defaults_to_empty_list():
    item = ComplianceConclusion(
        conclusion="结论正文",
        risk_level="中",
        clause_refs=["AML-12-3"],
        confidence=0.6,
    )
    assert item.evidence_quotes == []


def test_clause_refs_are_stripped_and_blanks_dropped():
    item = ComplianceConclusion(
        conclusion="结论正文",
        risk_level="中",
        clause_refs=["  AML-12-3 ", "", "   ", " CSRC-2024-17"],
        confidence=0.6,
    )
    assert item.clause_refs == ["AML-12-3", "CSRC-2024-17"]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "conclusion": "测试",
            "risk_level": "低",
            "clause_refs": [],
            "confidence": 0.5,
        },
        {
            "conclusion": "测试",
            "risk_level": "未知",
            "clause_refs": ["A-1"],
            "confidence": 0.5,
        },
        {
            "conclusion": "测试",
            "risk_level": "高",
            "clause_refs": ["A-1"],
            "confidence": 1.2,
        },
        {
            "conclusion": "测试",
            "risk_level": "高",
            "clause_refs": ["A-1"],
            "confidence": 0.99,
        },
        {
            "conclusion": "",
            "risk_level": "低",
            "clause_refs": ["A-1"],
            "confidence": 0.5,
        },
    ],
)
def test_invalid_compliance_conclusion(payload):
    with pytest.raises(ValidationError):
        ComplianceConclusion(**payload)
