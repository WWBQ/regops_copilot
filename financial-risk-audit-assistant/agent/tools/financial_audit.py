"""通过已配置的 RegOps 服务读取财务事实和年报证据；不提供写入能力。"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import requests
from langchain_core.tools import tool

from agent.env_utils import get_env


_CONCEPTS = {
    "revenue", "net_profit", "total_assets", "total_liabilities",
    "total_equity", "operating_cash_flow",
}
_MAX_FACT_PAGES = 10
_PAGE_SIZE = 500


def _result(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _service_config() -> tuple[str, str] | None:
    token = get_env("REGOPS_SERVICE_TOKEN").strip()
    if not token:
        return None
    base_url = get_env("REGOPS_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return base_url, token


def _request_json(method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    configured = _service_config()
    if configured is None:
        raise RuntimeError("未配置 REGOPS_SERVICE_TOKEN 或 REGOPS_API_BASE_URL 无效")
    base_url, token = configured
    try:
        response = requests.request(
            method,
            f"{base_url}{path}",
            params=params,
            json=body,
            headers={"X-Regops-Service-Token": token},
            timeout=15,
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise RuntimeError(f"RegOps 服务返回 HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("RegOps 服务返回格式不正确")
        return payload
    except requests.RequestException as exc:
        # 不把请求头、URL 或可能含凭据的原始异常交给模型。
        raise RuntimeError("RegOps 服务不可访问或请求超时") from exc
    except ValueError as exc:
        raise RuntimeError("RegOps 服务返回了无效 JSON") from exc


def _fact_rows(company_code: str, concept: str) -> list[dict]:
    rows: list[dict] = []
    for page in range(_MAX_FACT_PAGES):
        payload = _request_json(
            "GET",
            "/ops/quality/facts",
            params={
                "company_code": company_code,
                "concept": concept,
                "limit": _PAGE_SIZE,
                "offset": page * _PAGE_SIZE,
            },
        )
        items = payload.get("items")
        total = payload.get("total")
        if not isinstance(items, list) or not isinstance(total, int) or total < 0:
            raise RuntimeError("财务事实接口返回格式不正确")
        rows.extend(item for item in items if isinstance(item, dict))
        if len(rows) >= total:
            return rows
    raise RuntimeError("财务事实超过查询上限；拒绝基于不完整数据分析")


def _accepted_fact(rows: list[dict], *, company_code: str, concept: str, year: int) -> dict:
    matching = [
        row for row in rows
        if row.get("company_code") == company_code
        and row.get("concept") == concept
        and str(row.get("period") or "") == f"{year}-12-31"
        and row.get("scope") == "consolidated"
    ]
    accepted = [row for row in matching if row.get("status") == "auto_accepted"]
    if not accepted:
        return {
            "year": year,
            "outcome": "unverified" if matching else "missing",
            "review_required": bool(matching),
        }
    try:
        values = {Decimal(str(row["value_yuan"])) for row in accepted}
    except (KeyError, InvalidOperation, TypeError):
        return {"year": year, "outcome": "invalid_value", "review_required": True}
    if not all(value.is_finite() for value in values):
        return {"year": year, "outcome": "invalid_value", "review_required": True}
    if len(values) != 1 or not all(row.get("currency") == "CNY" for row in accepted):
        return {"year": year, "outcome": "conflict", "review_required": True}
    sources = [
        {"doc_id": row.get("doc_id"), "page": row.get("page_no"), "fact_key": row.get("fact_key")}
        for row in accepted
        if row.get("doc_id") and type(row.get("page_no")) is int and row["page_no"] > 0
    ]
    if not sources:
        return {"year": year, "outcome": "missing_provenance", "review_required": True}
    return {
        "year": year,
        "outcome": "ok",
        "value_yuan": str(next(iter(values))),
        "currency": "CNY",
        "scope": "consolidated",
        "sources": sources[:5],
    }


@tool("lookup_financial_facts", parse_docstring=True)
def lookup_financial_facts(company_code: str, concept: str, years: list[int]) -> str:
    """查询上市公司已入库、经质量门认可的合并报表财务事实。

    Args:
        company_code: 六位证券代码，例如 000333。
        concept: 标准指标名，例如 revenue、net_profit、operating_cash_flow。
        years: 需要查询的年份，最多五个。
    """

    if not re.fullmatch(r"\d{6}", company_code):
        return _result(status="invalid_input", reason="company_code 必须为六位数字")
    if concept not in _CONCEPTS:
        return _result(status="invalid_input", reason=f"concept 不支持；可用：{', '.join(sorted(_CONCEPTS))}")
    if not years or len(years) > 5 or any(type(year) is not int or year < 2000 or year > 2100 for year in years):
        return _result(status="invalid_input", reason="years 必须为 2000—2100 年之间的 1—5 个年份")
    try:
        rows = _fact_rows(company_code, concept)
        facts = [_accepted_fact(rows, company_code=company_code, concept=concept, year=year) for year in sorted(set(years))]
    except RuntimeError as exc:
        return _result(status="unavailable", reason=str(exc))
    return _result(status="ok", company_code=company_code, concept=concept, facts=facts)


@tool("search_report_evidence", parse_docstring=True)
def search_report_evidence(company_code: str, year: int, question: str) -> str:
    """检索指定公司及年份的公开年报披露，只返回可定位到原文的候选证据。

    Args:
        company_code: 六位证券代码。
        year: 年报年份。
        question: 需要核查的叙述性问题，不能包含指令或凭据。
    """

    if not re.fullmatch(r"\d{6}", company_code) or type(year) is not int or not 2000 <= year <= 2100:
        return _result(status="invalid_input", reason="公司代码或年份无效")
    if not question.strip() or len(question) > 500:
        return _result(status="invalid_input", reason="问题必须为 1—500 字")
    try:
        payload = _request_json(
            "POST", "/chat",
            body={"message": f"{company_code} {year}年年报：{question}", "use_rag": True, "temperature": 0.0},
        )
    except RuntimeError as exc:
        return _result(status="unavailable", reason=str(exc))
    citations = payload.get("citations")
    matching = [
        {"doc_id": citation["doc_id"], "page": citation["page"], "snippet": citation["snippet"]}
        for citation in citations if isinstance(citation, dict)
        and str(citation.get("doc_id") or "").startswith(f"{company_code}_{year}")
        and isinstance(citation.get("page"), int) and citation["page"] > 0
        and isinstance(citation.get("snippet"), str) and citation["snippet"].strip()
    ] if isinstance(citations, list) else []
    if not payload.get("rag_used") or not matching:
        return _result(status="insufficient_evidence", reason="未找到该公司该年份的可定位年报证据")
    return _result(
        status="ok", company_code=company_code, year=year,
        citations=matching[:8],
        warning="仅返回候选原文片段；需人工核对原始年报后才能作为审计证据。",
    )
