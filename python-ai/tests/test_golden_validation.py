from __future__ import annotations

import json
from pathlib import Path

from app.eval.golden_validation import validate_rag_retrieval_golden


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _item(**overrides):
    value = {
        "id": "rag-001",
        "category": "strategy",
        "question": "美的2024年战略",
        "doc_id": "000333_2024",
        "company_code": "000333",
        "report_year": 2024,
        "gold_pages": [10],
        "probe_keywords": ["战略"],
    }
    value.update(overrides)
    return value


def test_structural_validation_accepts_consistent_golden(tmp_path: Path):
    path = _write(
        tmp_path / "golden.json",
        {"category_counts": {"strategy": 1}, "items": [_item()]},
    )
    report = validate_rag_retrieval_golden(path, expected_count=1, check_corpus=False)
    assert report["status"] == "passed"
    assert report["error_count"] == 0


def test_structural_validation_rejects_scope_and_duplicate_pages(tmp_path: Path):
    path = _write(
        tmp_path / "golden.json",
        {
            "category_counts": {"strategy": 1},
            "items": [_item(doc_id="wrong", gold_pages=[10, 10])],
        },
    )
    report = validate_rag_retrieval_golden(path, expected_count=1, check_corpus=False)
    codes = {error["code"] for error in report["errors"]}
    assert report["status"] == "failed"
    assert "doc_scope_mismatch" in codes
    assert "duplicate_gold_page" in codes


def test_duplicate_json_keys_are_reported(tmp_path: Path):
    path = tmp_path / "golden.json"
    path.write_text(
        '{"category_counts":{"strategy":1},"items":[{"id":"a","id":"b"}]}',
        encoding="utf-8",
    )
    report = validate_rag_retrieval_golden(path, expected_count=1, check_corpus=False)
    assert any(error["code"] == "duplicate_json_key" for error in report["errors"])
