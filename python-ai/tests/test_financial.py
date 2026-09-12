"""W2-2：G1 金额一致性 / G2 勾稽 / G3 证据坐标 + F10 抽取。"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.ingest.facts import FinancialFact
from app.ingest.financial import apply_gates, extract_and_gate, extract_facts_from_bundle
from app.ingest.reconciliation import check_r01, check_r02, check_r03, check_r04, run_reconciliation
from app.ingest.validation import (
    CRITICAL_CONCEPTS,
    amount_mismatch,
    detect_amount_conflicts,
    normalize_amount,
    resolve_concept,
    validate_bbox,
    validate_fact_evidence,
)


def _write_bundle(
    root: Path,
    *,
    code: str = "999999",
    year: int = 2024,
    balance: dict | None = None,
    income: dict | None = None,
    cashflow: dict | None = None,
) -> Path:
    directory = root / f"{code}_{year}"
    directory.mkdir(parents=True)
    period = f"{year}-12-31"
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "stock_code": code,
                "report_year": year,
                "report_date": period,
                "structured_fallback": {"source": "eastmoney_f10"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    files = {
        "balance": {
            "TOTAL_ASSETS": 1_000_000,
            "TOTAL_LIABILITIES": 400_000,
            "TOTAL_EQUITY": 600_000,
            **(balance or {}),
        },
        "income": {
            "TOTAL_OPERATE_INCOME": 500_000,
            "NETPROFIT": 60_000,
            "TOTAL_PROFIT": 80_000,
            "INCOME_TAX": 20_000,
            "BASIC_EPS": "1.50",
            "PARENT_NETPROFIT": 55_000,
            "MINORITY_INTEREST": 5_000,
            **(income or {}),
        },
        "cashflow": {
            "NETCASH_OPERATE": 30_000,
            "END_BAL_CASH": 120_000,
            "BEGIN_BAL_CASH": 100_000,
            "CCE_ADD": 20_000,
            **(cashflow or {}),
        },
    }
    endpoints = {"balance": "ZCFZB", "income": "LRB", "cashflow": "XJLLB"}
    for stem, row in files.items():
        payload = {
            "source": "eastmoney_f10",
            "endpoint": endpoints[stem],
            "report_date": period,
            "sec_code": f"{code}.SZ",
            "data": row,
        }
        (directory / f"{stem}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def _fact(**kwargs) -> FinancialFact:
    base = dict(
        company_code="999999",
        doc_id="999999_2024",
        concept="total_assets",
        period="2024-12-31",
        scope="consolidated",
        statement="balance_sheet",
        value=Decimal("1000"),
        raw_name="资产总计",
        raw_value="1000",
        source_type="web",
        content_hash="sha256:" + "a" * 64,
    )
    base.update(kwargs)
    return FinancialFact(**base)


def test_normalize_amount_units_and_missing():
    assert normalize_amount("1,234.56", "万元") == Decimal("12345600")
    assert normalize_amount("3.4", "亿元") == Decimal("340000000")
    assert normalize_amount("(100)", "元") == Decimal("-100")
    assert normalize_amount("-20", "元") == Decimal("-20")
    assert normalize_amount("—", "元") is None
    assert normalize_amount("N/A", "万元") is None
    assert normalize_amount(5000, "元") == Decimal("5000")


def test_aliases_cover_critical_concepts():
    mapped = {
        resolve_concept("营业收入"),
        resolve_concept("营业总收入"),
        resolve_concept("净利润"),
        resolve_concept("资产总计"),
        resolve_concept("负债合计"),
        resolve_concept("所有者权益合计"),
        resolve_concept("经营活动产生的现金流量净额"),
        resolve_concept("期末现金及现金等价物余额"),
        resolve_concept("基本每股收益"),
    }
    assert CRITICAL_CONCEPTS <= mapped


def test_g1_same_fact_mismatch_and_unit_shift():
    left = {
        "concept": "revenue",
        "period": "2024-12-31",
        "scope": "consolidated",
        "currency": "CNY",
        "statement": "income",
        "value": normalize_amount("10", "万元"),
    }
    right = {
        **left,
        "value": normalize_amount("10", "元"),
    }
    mismatched, reason = amount_mismatch(left, right)
    assert mismatched is True
    assert "金额不一致" in reason

    same = {**right, "value": Decimal("100000")}
    mismatched, _ = amount_mismatch(left, same)
    assert mismatched is False


def test_g1_duplicate_fact_key_conflict():
    facts = [
        {
            "concept": "total_assets",
            "period": "2024-12-31",
            "scope": "consolidated",
            "currency": "CNY",
            "statement": "balance_sheet",
            "value": Decimal("100"),
            "raw_name": "资产总计",
        },
        {
            "concept": "total_assets",
            "period": "2024-12-31",
            "scope": "consolidated",
            "currency": "CNY",
            "statement": "balance_sheet",
            "value": Decimal("110"),
            "raw_name": "资产合计",
        },
    ]
    conflicts = detect_amount_conflicts(facts)
    assert len(conflicts) == 1
    assert conflicts[0]["reason"] == "critical_amount_mismatch"


def test_g2_pass_and_fail_r01_r02_r03_r04():
    ok = {
        "total_assets": Decimal("1000"),
        "total_liabilities": Decimal("400"),
        "total_equity": Decimal("600"),
        "cash_end": Decimal("120"),
        "cash_begin": Decimal("100"),
        "net_cash_change": Decimal("20"),
        "net_profit": Decimal("60"),
        "profit_before_tax": Decimal("80"),
        "income_tax": Decimal("20"),
        "net_profit_attributable": Decimal("55"),
        "minority_interest": Decimal("5"),
    }
    results = run_reconciliation(ok)
    assert [item.rule_id for item in results] == ["R01", "R02", "R03", "R04"]
    assert all(item.passed for item in results)
    assert not any(item.skipped for item in results)

    bad_equity = {**ok, "total_equity": Decimal("500")}
    r01 = check_r01(bad_equity)
    assert r01.passed is False
    assert "勾稽失败" in r01.message

    r02 = check_r02({**ok, "cash_end": Decimal("999")})
    assert r02.passed is False
    r03 = check_r03({**ok, "net_profit": Decimal("1")})
    assert r03.passed is False
    r04 = check_r04({**ok, "minority_interest": Decimal("1")})
    assert r04.passed is False
    assert "归母勾稽失败" in r04.message


def test_r04_skips_when_minority_missing():
    values = {
        "net_profit": Decimal("60"),
        "net_profit_attributable": Decimal("55"),
    }
    result = check_r04(values)
    assert result.skipped is True
    assert result.passed is True
    assert "跳过" in result.message
    results = run_reconciliation(values)
    r04 = next(item for item in results if item.rule_id == "R04")
    assert r04.skipped is True
    assert r04.passed is True


def test_resolve_minority_interest_alias():
    assert resolve_concept("少数股东损益") == "minority_interest"
    assert resolve_concept("MINORITY_INTEREST") == "minority_interest"


def test_g3_pdf_bbox_required_web_hash_ok():
    ok, _ = validate_bbox(12, [10, 20, 40, 50], page_width=100, page_height=200)
    assert ok is True
    failed, reason = validate_bbox(12, None)
    assert failed is False
    assert "bbox" in reason.lower() or "BBox" in reason

    web_ok, _ = validate_fact_evidence(
        {"source_type": "web", "content_hash": "sha256:" + "b" * 64}
    )
    assert web_ok is True
    web_fail, reason = validate_fact_evidence({"source_type": "web", "content_hash": ""})
    assert web_fail is False
    assert "content_hash" in reason


def test_extract_f10_and_gates_pass(tmp_path: Path):
    directory = _write_bundle(tmp_path)
    facts = extract_facts_from_bundle(directory)
    concepts = {fact.concept for fact in facts}
    assert CRITICAL_CONCEPTS <= concepts
    report = extract_and_gate(directory)
    assert report.g1_passed
    assert report.g2_passed
    assert report.g3_passed
    assert report.missing_critical == []
    assert report.auto_accepted == len(report.facts)
    assert all(fact.status == "auto_accepted" for fact in report.facts)


def test_g2_fail_marks_human_review(tmp_path: Path):
    directory = _write_bundle(tmp_path, balance={"TOTAL_EQUITY": 1})
    report = extract_and_gate(directory)
    assert report.g2_passed is False
    equity = next(fact for fact in report.facts if fact.concept == "total_equity")
    assert equity.status == "human_review"
    assert "reconciliation_failed:R01" in (equity.review_reason or "")
    revenue = next(fact for fact in report.facts if fact.concept == "revenue")
    assert revenue.status == "auto_accepted"


def test_g1_alias_conflict_not_silently_picked(tmp_path: Path):
    directory = _write_bundle(
        tmp_path,
        income={"TOTAL_OPERATE_INCOME": 500_000, "OPERATE_INCOME": 480_000},
    )
    report = extract_and_gate(directory)
    assert report.g1_passed is False
    revenue_facts = [fact for fact in report.facts if fact.concept == "revenue"]
    assert len(revenue_facts) == 1
    assert revenue_facts[0].status == "human_review"


def test_pdf_missing_bbox_blocked():
    fact = _fact(source_type="pdf", content_hash=None, page_no=None, bbox=None, concept="net_profit")
    report = apply_gates([fact])
    assert report.g3_passed is False
    assert report.facts[0].status == "human_review"
    assert "missing_or_invalid_bbox" in (report.facts[0].review_reason or "")


def test_gold_parser_mismatch_goes_to_review():
    extracted = _fact(concept="revenue", statement="income", value=Decimal("10"))
    gold = _fact(concept="revenue", statement="income", value=Decimal("11"), parser="gold")
    report = apply_gates([extracted], gold_facts=[gold])
    assert report.g1_passed is False
    assert report.facts[0].status == "human_review"
