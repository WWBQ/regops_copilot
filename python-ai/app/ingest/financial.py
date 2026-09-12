"""F10 / 结构化三表 → Financial Fact，过 G1/G2/G3 后写入 fin_metric。

数字来源优先东方财富 F10 JSON（data/raw/xbrl），不从 PDF 表格猜数、
不手算 ROE / 毛利率 / EPS。PDF bbox 仍走 G3 的 pdf 分支，供后续交叉验证。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from app.config import ROOT_DIR
from app.ingest.facts import FinancialFact, parse_period, yuan_str
from app.ingest.reconciliation import DISPLAY_UNIT_YUAN, RuleResult, run_reconciliation
from app.ingest.validation import (
    CRITICAL_CONCEPTS,
    UNIT_SCALE,
    detect_amount_conflicts,
    normalize_amount,
    validate_fact_evidence,
)

logger = logging.getLogger(__name__)

GOLDEN_CODES = ("002594", "601633", "000333", "000651", "600031")
DEFAULT_F10_ROOT = ROOT_DIR / "data" / "raw" / "xbrl"
DEFAULT_SCOPE = "consolidated"
DEFAULT_UNIT = "元"
PARSER_F10 = "eastmoney_f10"

STATEMENT_FILES = {
    "balance": "balance_sheet",
    "income": "income",
    "cashflow": "cash_flow",
}


@dataclass(frozen=True)
class ConceptSpec:
    concept: str
    statement: str
    file_stem: str
    keys: tuple[str, ...]
    display_name: str


CONCEPT_SPECS: tuple[ConceptSpec, ...] = (
    ConceptSpec(
        "total_assets",
        "balance_sheet",
        "balance",
        ("资产总计", "资产合计", "TOTAL_ASSETS"),
        "资产总计",
    ),
    ConceptSpec(
        "total_liabilities",
        "balance_sheet",
        "balance",
        ("负债合计", "负债总计", "TOTAL_LIABILITIES"),
        "负债合计",
    ),
    ConceptSpec(
        "total_equity",
        "balance_sheet",
        "balance",
        (
            "所有者权益（或股东权益）合计",
            "所有者权益合计",
            "股东权益合计",
            "TOTAL_EQUITY",
        ),
        "所有者权益合计",
    ),
    ConceptSpec(
        "revenue",
        "income",
        "income",
        (
            "营业总收入",
            "TOTAL_OPERATE_INCOME",
            "TOTALOPERATEREVE",
            "营业收入",
            "OPERATE_INCOME",
            "OPERATEREVE",
        ),
        "营业总收入",
    ),
    ConceptSpec(
        "net_profit",
        "income",
        "income",
        ("净利润", "NETPROFIT", "NET_PROFIT"),
        "净利润",
    ),
    ConceptSpec(
        "net_profit_attributable",
        "income",
        "income",
        (
            "归属于母公司股东的净利润",
            "归属于母公司所有者的净利润",
            "PARENT_NETPROFIT",
            "PARENTNETPROFIT",
            "PARENT_NET_PROFIT",
        ),
        "归属于母公司股东的净利润",
    ),
    ConceptSpec(
        "minority_interest",
        "income",
        "income",
        (
            "少数股东损益",
            "少数股东净利润",
            "MINORITY_INTEREST",
            "MINORITYINTEREST",
            "MINORITY_PROFIT",
        ),
        "少数股东损益",
    ),
    ConceptSpec(
        "profit_before_tax",
        "income",
        "income",
        ("利润总额", "TOTAL_PROFIT", "SUMPROFIT", "SUM_PROFIT"),
        "利润总额",
    ),
    ConceptSpec(
        "income_tax",
        "income",
        "income",
        ("所得税费用", "INCOME_TAX", "INCOMETAX"),
        "所得税费用",
    ),
    ConceptSpec(
        "eps",
        "income",
        "income",
        ("基本每股收益", "BASIC_EPS", "BASICEPS"),
        "基本每股收益",
    ),
    ConceptSpec(
        "operating_cash_flow",
        "cash_flow",
        "cashflow",
        (
            "经营活动产生的现金流量净额",
            "NETCASH_OPERATE",
            "NETCASHOPERATE",
            "NET_CASH_OPERATE",
        ),
        "经营活动产生的现金流量净额",
    ),
    ConceptSpec(
        "cash_end",
        "cash_flow",
        "cashflow",
        (
            "期末现金及现金等价物余额",
            "END_BAL_CASH",
            "END_CASH",
            "CASHEQUIVEND",
            "CASH_EQUIV_END",
            "END_CASH_EQUIVALENTS",
        ),
        "期末现金及现金等价物余额",
    ),
    ConceptSpec(
        "cash_begin",
        "cash_flow",
        "cashflow",
        (
            "期初现金及现金等价物余额",
            "BEGIN_BAL_CASH",
            "BEGIN_CASH",
            "CASHEQUIVBEGIN",
            "CASH_EQUIV_BEGIN",
        ),
        "期初现金及现金等价物余额",
    ),
    ConceptSpec(
        "net_cash_change",
        "cash_flow",
        "cashflow",
        (
            "现金及现金等价物净增加额",
            "CCE_ADD",
            "NETCASH_EQUIV",
            "CASHNETEQUIV",
            "NET_INCREASE_CASH",
            "CASH_EQUIVALENTS_INCREASE",
        ),
        "现金及现金等价物净增加额",
    ),
)


@dataclass
class GateReport:
    company_code: str
    doc_id: str
    period: str
    scope: str
    facts: list[FinancialFact]
    g1_conflicts: list[dict[str, Any]]
    g2_results: list[RuleResult]
    g3_failures: list[dict[str, Any]]
    missing_critical: list[str]
    source: str = PARSER_F10
    display_unit: str = DEFAULT_UNIT

    @property
    def g1_passed(self) -> bool:
        return not self.g1_conflicts

    @property
    def g2_passed(self) -> bool:
        return all(item.passed or item.skipped for item in self.g2_results)

    @property
    def g3_passed(self) -> bool:
        return not self.g3_failures

    @property
    def auto_accepted(self) -> int:
        return sum(1 for fact in self.facts if fact.status == "auto_accepted")

    @property
    def human_review(self) -> int:
        return sum(1 for fact in self.facts if fact.status == "human_review")

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_code": self.company_code,
            "doc_id": self.doc_id,
            "period": self.period,
            "scope": self.scope,
            "source": self.source,
            "display_unit": self.display_unit,
            "fact_count": len(self.facts),
            "auto_accepted": self.auto_accepted,
            "human_review": self.human_review,
            "missing_critical": self.missing_critical,
            "g1": {"passed": self.g1_passed, "conflicts": self.g1_conflicts},
            "g2": {
                "passed": self.g2_passed,
                "rules": [item.to_dict() for item in self.g2_results],
            },
            "g3": {
                "passed": self.g3_passed,
                "policy": "web_content_hash" if all(f.source_type == "web" for f in self.facts) else "pdf_bbox",
                "failed": self.g3_failures,
            },
            "facts": [fact.to_gate_dict() for fact in self.facts],
        }


def _row_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    if isinstance(data, dict):
        return data
    return payload if isinstance(payload, dict) else {}


def _lookup_keys(row: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key in row:
        mapping[str(key)] = str(key)
        mapping[str(key).upper()] = str(key)
    return mapping


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> list[tuple[str, Any]]:
    index = _lookup_keys(row)
    hits: list[tuple[str, Any]] = []
    seen_actual: set[str] = set()
    for candidate in keys:
        actual = index.get(candidate) or index.get(candidate.upper())
        if actual is None or actual in seen_actual:
            continue
        seen_actual.add(actual)
        hits.append((actual, row[actual]))
    return hits


def _detect_unit(payload: dict[str, Any], row: dict[str, Any]) -> str:
    for key in ("unit", "UNIT", "display_unit", "货币单位"):
        raw = payload.get(key) or row.get(key)
        if isinstance(raw, str) and raw.strip() in UNIT_SCALE:
            return raw.strip()
    return DEFAULT_UNIT


def _bundle_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _dir_identity(directory: Path, manifest: dict[str, Any]) -> tuple[str, int, str]:
    code = str(manifest.get("stock_code") or "")
    year = manifest.get("report_year")
    period = str(manifest.get("report_date") or "")
    match = re.fullmatch(r"(\d{6})_(\d{4})", directory.name)
    if match:
        code = code or match.group(1)
        year = year or int(match.group(2))
    if not code or year is None:
        raise ValueError(f"cannot infer company/year from {directory}")
    if not period:
        period = f"{int(year)}-12-31"
    return code, int(year), parse_period(period)


def load_f10_bundle(directory: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    payloads: dict[str, dict[str, Any]] = {}
    files: list[Path] = []
    for stem in STATEMENT_FILES:
        path = directory / f"{stem}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        payloads[stem] = json.loads(path.read_text(encoding="utf-8"))
        files.append(path)
    return manifest, payloads, _bundle_hash(files)


def extract_facts_from_bundle(
    directory: Path,
    *,
    source_type: str = "web",
    scope: str = DEFAULT_SCOPE,
) -> list[FinancialFact]:
    manifest, payloads, digest = load_f10_bundle(directory)
    company_code, year, period = _dir_identity(directory, manifest)
    doc_id = f"{company_code}_{year}"
    facts: list[FinancialFact] = []

    for spec in CONCEPT_SPECS:
        payload = payloads[spec.file_stem]
        row = _row_from_payload(payload)
        unit = _detect_unit(payload, row)
        if not period:
            period = parse_period(payload.get("report_date") or row.get("REPORT_DATE") or row.get("REPORTDATE"))
        observations: list[tuple[str, Decimal, str]] = []
        hits = _first_present(row, spec.keys)
        # 多数科目只取优先级最高的一个字段；营收保留多别名供 G1 比对。
        if spec.concept != "revenue":
            hits = hits[:1]
        for actual_key, raw in hits:
            value = normalize_amount(raw, unit)
            if value is None:
                continue
            observations.append((actual_key, value, str(raw)))
        if not observations:
            logger.warning("missing concept %s in %s %s", spec.concept, company_code, spec.file_stem)
            continue
        unique_values = {format(item[1], "f") for item in observations}
        if len(unique_values) == 1:
            actual_key, value, raw = observations[0]
            facts.append(
                FinancialFact(
                    company_code=company_code,
                    doc_id=doc_id,
                    concept=spec.concept,
                    period=period,
                    scope=scope,
                    statement=spec.statement,
                    value=value,
                    raw_name=spec.display_name,
                    raw_value=raw,
                    source_type=source_type,
                    unit_raw=unit,
                    parser=PARSER_F10,
                    xbrl_tag=actual_key,
                    content_hash=digest,
                )
            )
            continue
        for actual_key, value, raw in observations:
            facts.append(
                FinancialFact(
                    company_code=company_code,
                    doc_id=doc_id,
                    concept=spec.concept,
                    period=period,
                    scope=scope,
                    statement=spec.statement,
                    value=value,
                    raw_name=actual_key,
                    raw_value=raw,
                    source_type=source_type,
                    unit_raw=unit,
                    parser=PARSER_F10,
                    xbrl_tag=actual_key,
                    content_hash=digest,
                )
            )
    return facts


def _concept_values(facts: list[FinancialFact]) -> dict[str, Decimal | None]:
    values: dict[str, Decimal | None] = {}
    conflicts: set[str] = set()
    for fact in facts:
        previous = values.get(fact.concept)
        if fact.concept in values and previous != fact.value:
            conflicts.add(fact.concept)
        values[fact.concept] = fact.value
    for concept in conflicts:
        values[concept] = None
    return values


def apply_gates(
    facts: list[FinancialFact],
    *,
    display_unit: Decimal | None = None,
    gold_facts: list[FinancialFact] | None = None,
) -> GateReport:
    if not facts:
        raise ValueError("no financial facts to validate")
    sample = facts[0]
    unit_name = sample.unit_raw or DEFAULT_UNIT
    unit = display_unit or UNIT_SCALE.get(unit_name, DISPLAY_UNIT_YUAN)

    gate_dicts = [fact.to_gate_dict() for fact in facts]
    if gold_facts:
        gate_dicts.extend(item.to_gate_dict() for item in gold_facts)
    g1_conflicts = detect_amount_conflicts(gate_dicts)

    g2_results = run_reconciliation(_concept_values(facts), display_unit=unit)
    failed_g2_concepts = {
        concept
        for item in g2_results
        if not item.passed and not item.skipped
        for concept in item.concepts
    }

    g3_failures: list[dict[str, Any]] = []
    g3_failed_keys: set[str] = set()
    for fact in facts:
        ok, reason = validate_fact_evidence(fact.to_gate_dict())
        if not ok:
            g3_failures.append({"fact_key": fact.fact_key_id, "reason": reason})
            g3_failed_keys.add(fact.fact_key_id)

    conflict_keys = {item["fact_key"] for item in g1_conflicts}
    gated: list[FinancialFact] = []
    for fact in facts:
        reasons: list[str] = []
        if fact.fact_key_id in conflict_keys:
            reasons.append("critical_amount_mismatch")
        if fact.concept in failed_g2_concepts:
            failed_rules = [item.rule_id for item in g2_results if not item.passed and fact.concept in item.concepts]
            reasons.append("reconciliation_failed:" + ",".join(failed_rules))
        if fact.fact_key_id in g3_failed_keys:
            reasons.append("missing_or_invalid_bbox")
        if reasons:
            gated.append(
                replace(
                    fact,
                    status="human_review",
                    review_reason="; ".join(reasons),
                )
            )
        else:
            gated.append(replace(fact, status="auto_accepted", review_reason=None))

    collapsed: dict[str, FinancialFact] = {}
    for fact in gated:
        previous = collapsed.get(fact.fact_key_id)
        if previous is None:
            collapsed[fact.fact_key_id] = fact
            continue
        reasons = [item for item in (previous.review_reason, fact.review_reason) if item]
        collapsed[fact.fact_key_id] = replace(
            previous,
            status="human_review" if "human_review" in {previous.status, fact.status} else previous.status,
            review_reason="; ".join(dict.fromkeys(reasons)) or previous.review_reason,
        )
    gated = list(collapsed.values())

    present = {fact.concept for fact in gated}
    missing = sorted(CRITICAL_CONCEPTS - present)
    return GateReport(
        company_code=sample.company_code,
        doc_id=sample.doc_id,
        period=sample.period,
        scope=sample.scope,
        facts=gated,
        g1_conflicts=g1_conflicts,
        g2_results=g2_results,
        g3_failures=g3_failures,
        missing_critical=missing,
        display_unit=unit_name,
    )


def extract_and_gate(directory: Path) -> GateReport:
    facts = extract_facts_from_bundle(directory)
    if facts:
        return apply_gates(facts)
    manifest, _, _ = load_f10_bundle(directory)
    company_code, year, period = _dir_identity(directory, manifest)
    return GateReport(
        company_code=company_code,
        doc_id=f"{company_code}_{year}",
        period=period,
        scope=DEFAULT_SCOPE,
        facts=[],
        g1_conflicts=[],
        g2_results=run_reconciliation({}),
        g3_failures=[],
        missing_critical=sorted(CRITICAL_CONCEPTS),
    )


def discover_f10_dirs(root: Path | None = None, *, codes: list[str] | None = None, year: int = 2024) -> list[Path]:
    root = (root or DEFAULT_F10_ROOT).resolve()
    wanted = list(codes or GOLDEN_CODES)
    found: list[Path] = []
    for code in wanted:
        path = root / f"{code}_{year}"
        if path.is_dir():
            found.append(path)
    return found


def format_yuan(value: Decimal | None) -> str:
    text = yuan_str(value)
    if text is None:
        return "—"
    amount = Decimal(text)
    abs_amount = abs(amount)
    if abs_amount >= Decimal("100000000"):
        return f"{amount / Decimal('100000000'):.2f} 亿元"
    if abs_amount >= Decimal("10000"):
        return f"{amount / Decimal('10000'):.2f} 万元"
    return f"{amount} 元"
