"""金融只读 MCP 服务：质量门读取 F10 事实，RAG 直接检索 PDF 年报证据。

主服务在 /mcp/ 挂载 HTTP 传输；也可单独以 stdio 运行供本地调试。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import requests
from fastmcp import FastMCP

from app.config import get_settings
from app.db.connection import get_connection
from app.rag.service import retrieve_relevant_hits_for_docs


mcp = FastMCP("RegOps Financial Read-Only")
logger = logging.getLogger(__name__)

_CONCEPTS = frozenset({
    "revenue", "net_profit", "total_assets", "total_liabilities",
    "total_equity", "operating_cash_flow",
})
_PAGE_SIZE = 500
_MAX_FACT_PAGES = 10


def _service_config() -> tuple[str, str]:
    settings = get_settings()
    token = settings.service_token.strip()
    base_url = settings.regops_api_base_url.rstrip("/")
    parsed = urlparse(base_url)
    if not token or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise RuntimeError("财务数据服务未正确配置")
    return base_url, token


def _request_json(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    base_url, token = _service_config()
    try:
        response = requests.request(
            method, f"{base_url}{path}", params=params, json=body,
            headers={"X-Regops-Service-Token": token},
            timeout=(5, 30),
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise RuntimeError(f"财务数据服务返回 HTTP {response.status_code}")
        payload = response.json()
    except requests.RequestException as exc:
        # 不向模型或 MCP 调用方泄漏请求 URL、令牌和底层异常。
        raise RuntimeError("财务数据服务不可访问或请求超时") from exc
    except ValueError as exc:
        raise RuntimeError("财务数据服务返回了无效 JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("财务数据服务返回格式不正确")
    return payload


def _fact_rows(company_code: str, concept: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(_MAX_FACT_PAGES):
        payload = _request_json(
            "GET", "/ops/quality/facts",
            params={"company_code": company_code, "concept": concept, "limit": _PAGE_SIZE, "offset": page * _PAGE_SIZE},
        )
        items, total = payload.get("items"), payload.get("total")
        if not isinstance(items, list) or type(total) is not int or total < 0 or total > _PAGE_SIZE * _MAX_FACT_PAGES:
            raise RuntimeError("财务事实接口返回格式不正确或数据超出查询上限")
        if any(not isinstance(item, dict) for item in items) or len(items) > _PAGE_SIZE:
            raise RuntimeError("财务事实接口返回格式不正确")
        rows.extend(items)
        if len(rows) >= total:
            return rows
        if not items:
            raise RuntimeError("财务事实分页不完整；拒绝基于不完整数据分析")
    raise RuntimeError("财务事实超过查询上限；拒绝基于不完整数据分析")


def _accepted_fact(rows: list[dict[str, Any]], *, company_code: str, concept: str, year: int) -> dict[str, Any]:
    # 当前 fin_metric 的确定性数值来自 F10；PDF 年报仅由证据检索工具读取。
    matching = [
        row for row in rows
        if row.get("company_code") == company_code
        and row.get("concept") == concept
        and row.get("period") == f"{year}-12-31"
        and row.get("scope") == "consolidated"
        and row.get("source_type") == "web"
        and row.get("parser") == "eastmoney_f10"
    ]
    accepted = [row for row in matching if row.get("status") in {"auto_accepted", "manually_accepted"}]
    if not accepted:
        return {"year": year, "outcome": "unverified" if matching else "missing", "review_required": bool(matching)}
    try:
        values = {Decimal(str(row["value_yuan"])) for row in accepted}
    except (KeyError, InvalidOperation, TypeError):
        return {"year": year, "outcome": "invalid_value", "review_required": True}
    if not all(value.is_finite() for value in values):
        return {"year": year, "outcome": "invalid_value", "review_required": True}
    if len(values) != 1 or any(row.get("currency") != "CNY" for row in accepted):
        return {"year": year, "outcome": "conflict", "review_required": True}

    # 每条 F10 事实独立核验入库时计算的完整 SHA-256；不能把同名 doc_id
    # 冒充 PDF 年报页码引用。
    sources: list[dict[str, Any]] = []
    expected_doc_id = f"{company_code}_{year}"
    for row in accepted:
        doc_id = row.get("doc_id")
        digest = row.get("content_hash")
        if doc_id != expected_doc_id or not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            return {"year": year, "outcome": "missing_provenance", "review_required": True}
        sources.append({
            "doc_id": doc_id,
            "source_type": "web",
            "parser": "eastmoney_f10",
            "content_hash": digest,
            "fact_key": row.get("fact_key"),
        })
    if len({source["content_hash"] for source in sources}) != 1:
        return {"year": year, "outcome": "conflict", "review_required": True}
    return {
        "year": year, "outcome": "ok", "value_yuan": str(next(iter(values))),
        "currency": "CNY", "scope": "consolidated",
        "sources": sources[:5],
    }


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def lookup_financial_facts(company_code: str, concept: str, years: list[int]) -> dict[str, Any]:
    """查询指定公司的已入库、质量门认可的合并报表财务事实。

    company_code 是六位证券代码；concept 可选 revenue、net_profit、
    total_assets、total_liabilities、total_equity、operating_cash_flow；
    years 为 1—5 个年份。只有 outcome=ok 的数值可用于初筛；sources 中
    source_type=web 是 F10 结构化数据，以入库 SHA-256 溯源，不是 PDF 年报页码。
    """
    if not re.fullmatch(r"[0-9]{6}", company_code):
        return {"status": "invalid_input", "reason": "company_code 必须为六位数字"}
    if concept not in _CONCEPTS:
        return {"status": "invalid_input", "reason": f"concept 不支持；可用：{', '.join(sorted(_CONCEPTS))}"}
    if not years or len(years) > 5 or any(type(year) is not int or not 2000 <= year <= 2100 for year in years):
        return {"status": "invalid_input", "reason": "years 必须为 2000—2100 年之间的 1—5 个年份"}
    try:
        rows = _fact_rows(company_code, concept)
    except RuntimeError as exc:
        return {"status": "unavailable", "reason": str(exc)}
    return {
        "status": "ok", "company_code": company_code, "concept": concept,
        "facts": [_accepted_fact(rows, company_code=company_code, concept=concept, year=year) for year in sorted(set(years))],
    }


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def search_report_evidence(company_code: str, year: int, question: str) -> dict[str, Any]:
    """检索指定公司、年份的年报，只返回可定位页码的候选原文片段。

    question 是需要查证的叙述性问题。返回的候选片段仍需人工核对原文；
    不返回模型生成的回答，也不把候选片段当作审计结论。
    """
    if not re.fullmatch(r"[0-9]{6}", company_code) or type(year) is not int or not 2000 <= year <= 2100:
        return {"status": "invalid_input", "reason": "公司代码或年份无效"}
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        return {"status": "invalid_input", "reason": "问题必须为 1—500 字"}
    doc_id = f"{company_code}_{year}"
    try:
        # 先用 pdf_document 的公司/年份/状态锁定唯一年报；检索 SQL 只会看到这个 doc_id。
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM pdf_document
                   WHERE doc_id = %s AND company_code = %s AND report_year = %s
                     AND doc_type = 'annual_report' AND ingest_status = 'ready'
                     AND is_active = TRUE
                   LIMIT 1""",
                (doc_id, company_code, year),
            )
            ready = cur.fetchone() is not None
        if not ready:
            return {"status": "insufficient_evidence", "reason": "该公司该年份的年报尚未完成入库"}

        settings = get_settings()
        # 工具只负责检索，不让“LLM 重排”配置触发另一次聊天模型调用。
        mode = "rerank" if settings.rag_rerank_enabled and settings.rag_rerank_backend == "bge" else "hybrid"
        hits, _pipeline = retrieve_relevant_hits_for_docs(
            question=question.strip(),
            doc_ids=[doc_id],
            top_k=8,
            min_score=settings.rag_min_score,
            mode=mode,
        )
    except Exception:
        logger.exception("financial report evidence retrieval failed")
        return {"status": "unavailable", "reason": "年报检索服务不可用"}

    citations = [
        {"doc_id": doc_id, "page": hit.metadata["page"], "snippet": hit.content.strip()[:500]}
        for hit in hits
        if hit.doc_id == doc_id
        and isinstance(hit.metadata, dict)
        and type(hit.metadata.get("page")) is int and hit.metadata["page"] > 0
        and isinstance(hit.content, str) and hit.content.strip()
    ]
    if not citations:
        return {"status": "insufficient_evidence", "reason": "未找到该公司该年份的可定位年报证据"}
    return {
        "status": "ok", "company_code": company_code, "year": year,
        "citations": citations[:8],
        "warning": "仅返回候选原文片段；需人工核对原始年报后才能作为审计证据。",
    }


if __name__ == "__main__":
    mcp.run()
