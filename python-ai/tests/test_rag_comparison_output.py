import json

from app.chat.schemas import Citation
from app.rag.comparison_output import (
    build_comparison_contract,
    validate_comparison_output,
)


def _contract():
    return build_comparison_contract(
        companies=[("000333", "美的集团"), ("000651", "格力电器")],
        periods=(2024,),
        citations=[
            Citation(doc_id="000333_2024", page=10, snippet="美的证据"),
            Citation(doc_id="000651_2024", page=12, snippet="格力证据"),
        ],
    )


def _payload() -> dict:
    return {
        "answer_type": "company_comparison",
        "comparison_allowed": True,
        "periods": [2024],
        "companies": [
            {
                "company_code": "000333",
                "company_name": "美的集团",
                "summary": "美的强调全球突破。",
                "citation_ids": [1],
            },
            {
                "company_code": "000651",
                "company_name": "格力电器",
                "summary": "格力强调核心技术。",
                "citation_ids": [2],
            },
        ],
        "similarities": [
            {"statement": "都重视技术能力。", "citation_ids": [1, 2]}
        ],
        "differences": [
            {"statement": "战略表达的侧重点不同。", "citation_ids": [1, 2]}
        ],
        "missing_evidence": [],
    }


def test_validate_comparison_output_accepts_grounded_schema():
    check = validate_comparison_output(
        f"```json\n{json.dumps(_payload(), ensure_ascii=False)}\n```",
        _contract(),
    )

    assert check.ok is True
    assert check.blocked is False
    assert check.comparison is not None
    assert "### 美的集团" in check.reply
    assert "[1][2]" in check.reply


def test_validate_comparison_output_rejects_cross_company_summary_citation():
    payload = _payload()
    payload["companies"][0]["citation_ids"] = [2]

    check = validate_comparison_output(
        json.dumps(payload, ensure_ascii=False),
        _contract(),
    )

    assert check.ok is False
    assert check.blocked is True
    assert check.comparison is None
    assert any("引用了其他公司的证据" in error for error in check.errors)


def test_validate_comparison_output_rejects_one_sided_difference():
    payload = _payload()
    payload["differences"][0]["citation_ids"] = [1]

    check = validate_comparison_output(
        json.dumps(payload, ensure_ascii=False),
        _contract(),
    )

    assert check.ok is False
    assert any("必须同时引用所有被比较公司" in error for error in check.errors)


def test_validate_comparison_output_allows_explicit_evidence_refusal():
    payload = _payload()
    payload["comparison_allowed"] = False
    payload["differences"] = []
    payload["missing_evidence"] = ["两家公司披露维度不一致"]

    check = validate_comparison_output(
        json.dumps(payload, ensure_ascii=False),
        _contract(),
    )

    assert check.ok is True
    assert check.blocked is True
    assert check.comparison is not None
    assert "现有证据不足以在同一维度上直接比较" in check.reply
