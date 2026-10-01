"""多公司比较的结构化输出解析、业务校验与展示文本渲染。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.chat.schemas import (
    Citation,
    CompanyComparisonResult,
    ComparisonClaim,
)
from app.rag.company_scope import company_code_from_doc_id

_CITATION_MARK_RE = re.compile(r"\[\s*\d+\s*\]")
BLOCK_PREFIX = "【比较结果校验拦截】"


@dataclass(frozen=True)
class ComparisonContract:
    companies: tuple[tuple[str, str], ...]
    periods: tuple[int, ...]
    citation_company_codes: tuple[str | None, ...]


@dataclass(frozen=True)
class ComparisonOutputCheck:
    ok: bool
    blocked: bool
    reply: str
    comparison: CompanyComparisonResult | None
    errors: tuple[str, ...] = ()

    def to_trace(self) -> dict[str, Any]:
        return {
            "name": "comparison_schema",
            "node": "comparison_schema",
            "ok": self.ok,
            "stop": self.blocked,
            "comparison_allowed": (
                self.comparison.comparison_allowed if self.comparison is not None else None
            ),
            "errors": list(self.errors),
        }


def build_comparison_contract(
    *,
    companies: list[tuple[str, str]],
    periods: tuple[int, ...],
    citations: list[Citation],
) -> ComparisonContract:
    return ComparisonContract(
        companies=tuple(companies),
        periods=periods,
        citation_company_codes=tuple(
            company_code_from_doc_id(citation.doc_id) for citation in citations
        ),
    )


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型没有返回 JSON 对象")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型 JSON 顶层必须是对象")
    return value


def _citation_codes(
    citation_ids: list[int],
    contract: ComparisonContract,
    errors: list[str],
    *,
    field: str,
) -> set[str]:
    codes: set[str] = set()
    total = len(contract.citation_company_codes)
    for citation_id in citation_ids:
        if citation_id < 1 or citation_id > total:
            errors.append(f"{field} 引用了不存在的片段 {citation_id}")
            continue
        code = contract.citation_company_codes[citation_id - 1]
        if code is None:
            errors.append(f"{field} 的片段 {citation_id} 无法识别公司")
            continue
        codes.add(code)
    return codes


def _validate_claims(
    claims: list[ComparisonClaim],
    contract: ComparisonContract,
    errors: list[str],
    *,
    field: str,
    require_all_companies: bool,
) -> None:
    expected = {code for code, _name in contract.companies}
    for index, claim in enumerate(claims, start=1):
        codes = _citation_codes(
            claim.citation_ids,
            contract,
            errors,
            field=f"{field}[{index}]",
        )
        if require_all_companies and codes != expected:
            errors.append(
                f"{field}[{index}] 必须同时引用所有被比较公司，实际为 {sorted(codes)}"
            )


def _business_errors(
    result: CompanyComparisonResult,
    contract: ComparisonContract,
) -> list[str]:
    errors: list[str] = []
    expected_names = dict(contract.companies)
    expected_codes = set(expected_names)
    actual_codes = [item.company_code for item in result.companies]
    if len(actual_codes) != len(set(actual_codes)):
        errors.append("companies 中存在重复公司")
    if set(actual_codes) != expected_codes:
        errors.append(
            f"公司集合不一致：期望 {sorted(expected_codes)}，实际 {sorted(actual_codes)}"
        )
    if set(result.periods) != set(contract.periods):
        errors.append(
            f"期间不一致：期望 {list(contract.periods)}，实际 {result.periods}"
        )

    for company in result.companies:
        expected_name = expected_names.get(company.company_code)
        if expected_name is not None and company.company_name != expected_name:
            errors.append(
                f"{company.company_code} 公司名称应为 {expected_name}，实际为 {company.company_name}"
            )
        codes = _citation_codes(
            company.citation_ids,
            contract,
            errors,
            field=f"companies[{company.company_code}]",
        )
        if codes and codes != {company.company_code}:
            errors.append(
                f"{company.company_code} 摘要引用了其他公司的证据 {sorted(codes)}"
            )

    _validate_claims(
        result.similarities,
        contract,
        errors,
        field="similarities",
        require_all_companies=True,
    )
    _validate_claims(
        result.differences,
        contract,
        errors,
        field="differences",
        require_all_companies=result.comparison_allowed,
    )

    if result.comparison_allowed:
        if result.missing_evidence:
            errors.append("comparison_allowed=true 时 missing_evidence 必须为空")
        if not result.differences:
            errors.append("comparison_allowed=true 时至少需要一条 differences")
    else:
        if not result.missing_evidence:
            errors.append("comparison_allowed=false 时必须说明 missing_evidence")
        if result.differences:
            errors.append("comparison_allowed=false 时不得输出 differences")
    return errors


def _clean_statement(text: str) -> str:
    return _CITATION_MARK_RE.sub("", text).strip()


def _markers(citation_ids: list[int]) -> str:
    unique = list(dict.fromkeys(citation_ids))
    return "".join(f"[{value}]" for value in unique)


def render_comparison(result: CompanyComparisonResult) -> str:
    period = "、".join(str(value) for value in sorted(set(result.periods)))
    lines = [f"比较期间：{period} 年。", ""]
    for company in result.companies:
        lines.extend(
            [
                f"### {company.company_name}",
                f"{_clean_statement(company.summary)} {_markers(company.citation_ids)}",
                "",
            ]
        )
    if result.similarities:
        lines.append("### 相同点")
        lines.extend(
            f"- {_clean_statement(claim.statement)} {_markers(claim.citation_ids)}"
            for claim in result.similarities
        )
        lines.append("")
    if result.comparison_allowed:
        lines.append("### 差异")
        lines.extend(
            f"- {_clean_statement(claim.statement)} {_markers(claim.citation_ids)}"
            for claim in result.differences
        )
    else:
        lines.append("### 证据限制")
        lines.append("现有证据不足以在同一维度上直接比较：")
        lines.extend(f"- {_clean_statement(item)}" for item in result.missing_evidence)
    return "\n".join(lines).strip()


def validate_comparison_output(
    raw: str,
    contract: ComparisonContract,
) -> ComparisonOutputCheck:
    try:
        payload = _extract_json(raw)
        result = CompanyComparisonResult.model_validate(payload)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        detail = str(exc).splitlines()[0]
        return ComparisonOutputCheck(
            ok=False,
            blocked=True,
            reply=f"{BLOCK_PREFIX}模型返回未通过结构校验，本次不展示比较结论。",
            comparison=None,
            errors=(detail,),
        )

    errors = _business_errors(result, contract)
    if errors:
        return ComparisonOutputCheck(
            ok=False,
            blocked=True,
            reply=f"{BLOCK_PREFIX}公司、期间或引用归属校验失败，本次不展示比较结论。",
            comparison=None,
            errors=tuple(errors),
        )
    return ComparisonOutputCheck(
        ok=True,
        blocked=not result.comparison_allowed,
        reply=render_comparison(result),
        comparison=result,
    )
