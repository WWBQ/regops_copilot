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
