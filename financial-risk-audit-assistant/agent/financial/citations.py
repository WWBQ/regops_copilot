"""为金融 MCP 工具结果分配引用编号，并转换成 RegOps 前端引用结构。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlencode

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage


@dataclass
class ToolCitationIndexer:
    """在一次 Agent 运行内为去重后的工具证据分配连续编号。"""

    _ids: dict[tuple[Any, ...], int] = field(default_factory=dict)

    def _id_for(self, key: tuple[Any, ...]) -> int:
        citation_id = self._ids.get(key)
        if citation_id is None:
            citation_id = len(self._ids) + 1
            self._ids[key] = citation_id
        return citation_id

    def annotate(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """给返回模型的事实或年报候选证据附加确定性 citation_id。"""

        result = deepcopy(payload)
        if tool_name == "lookup_financial_facts":
            company_code = str(result.get("company_code") or "")
            concept = str(result.get("concept") or "")
            for fact in result.get("facts") or []:
                if not isinstance(fact, dict) or fact.get("outcome") != "ok":
                    continue
                key = (
                    "facts", company_code, concept, fact.get("year"),
                    str(fact.get("value_yuan") or ""), str(fact.get("scope") or ""),
                )
                fact["citation_id"] = self._id_for(key)
        elif tool_name == "search_report_evidence":
            for citation in result.get("citations") or []:
                if not isinstance(citation, dict):
                    continue
                key = (
                    "document", str(citation.get("doc_id") or ""),
                    citation.get("page"), str(citation.get("snippet") or "").strip(),
                )
                citation["citation_id"] = self._id_for(key)
        elif tool_name == "search_external_risk_signals":
            for item in result.get("results") or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                if not url or not snippet:
                    continue
                key = (
                    "web", url, str(item.get("title") or "").strip(),
                    str(item.get("published_at") or "").strip(),
                    str(item.get("content_hash") or "").strip(),
                )
                item["citation_id"] = self._id_for(key)
        return result


def _content(message: Any) -> Any:
    if isinstance(message, BaseMessage):
        return message.content
    if isinstance(message, dict):
        return message.get("content")
    return None


def _is_tool_message(message: Any) -> bool:
    if isinstance(message, ToolMessage):
        return True
    if not isinstance(message, dict):
        return False
    return str(message.get("type") or "").lower() in {"tool", "toolmessage"}


def _payload(message: Any) -> dict[str, Any] | None:
    if not _is_tool_message(message):
        return None
    content = _content(message)
    if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
        content = content[0].get("text", content[0])
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _fact_citations(payload: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    company_code = str(payload.get("company_code") or "")
    concept = str(payload.get("concept") or "")
    result: list[tuple[int, dict[str, Any]]] = []
    for fact in payload.get("facts") or []:
        if not isinstance(fact, dict) or fact.get("outcome") != "ok":
            continue
        citation_id = fact.get("citation_id")
        if type(citation_id) is not int or citation_id <= 0:
            continue
        sources = fact.get("sources") or []
        source = sources[0] if sources and isinstance(sources[0], dict) else {}
        year = fact.get("year")
        value = str(fact.get("value_yuan") or "")
        query = urlencode({"company_code": company_code, "concept": concept})
        result.append(
            (
                citation_id,
                {
                    "citation_id": citation_id,
                    "doc_id": str(source.get("doc_id") or f"{company_code}_{year}"),
                    # facts 引用优先使用 href；page=1 只是兼容统一前端类型，不代表 PDF 页码。
                    "page": 1,
                    "snippet": f"{company_code} {year} 年 {concept}：{value} 元",
                    "title": f"财务事实库 · {company_code} {year} 年 {concept}",
                    "href": f"/quality/facts?{query}",
                    "kind": "facts",
                    "company_code": company_code,
                    "concept": concept,
                    "year": year,
                },
            )
        )
    return result


def _document_citations(payload: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    result: list[tuple[int, dict[str, Any]]] = []
    for item in payload.get("citations") or []:
        if not isinstance(item, dict):
            continue
        citation_id = item.get("citation_id")
        page = item.get("page")
        doc_id = str(item.get("doc_id") or "")
        snippet = str(item.get("snippet") or "").strip()
        if type(citation_id) is not int or citation_id <= 0 or type(page) is not int or page <= 0:
            continue
        if not doc_id or not snippet:
            continue
        result.append(
            (
                citation_id,
                {
                    "citation_id": citation_id,
                    "doc_id": doc_id,
                    "page": page,
                    "snippet": snippet,
                    "title": doc_id,
                    "href": None,
                    "kind": "document",
                },
            )
        )
    return result


def _web_citations(payload: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """把外部搜索结果转换成可点击的网页引用。"""

    result: list[tuple[int, dict[str, Any]]] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        citation_id = item.get("citation_id")
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        title = str(item.get("title") or item.get("publisher") or url).strip()
        if type(citation_id) is not int or citation_id <= 0 or not url or not snippet:
            continue
        result.append(
            (
                citation_id,
                {
                    "citation_id": citation_id,
                    "doc_id": url,
                    # 前端 Citation 保持统一结构；网页引用不展示页码。
                    "page": 0,
                    "snippet": snippet,
                    "title": title,
                    "href": url,
                    "kind": "web",
                    "publisher": str(item.get("publisher") or ""),
                    "published_at": str(item.get("published_at") or ""),
                    "fetched_at": str(item.get("fetched_at") or ""),
                    "content_hash": str(item.get("content_hash") or ""),
                    "source_tier": str(item.get("source_tier") or "public_web"),
                },
            )
        )
    return result


def citations_from_messages(messages: Iterable[Any]) -> list[dict[str, Any]]:
    """按 citation_id 汇总实际工具返回，供实时回答与 checkpoint 历史复用。"""

    indexed: dict[int, dict[str, Any]] = {}
    for message in messages:
        payload = _payload(message)
        if payload is None:
            continue
        if "facts" in payload:
            pairs = _fact_citations(payload)
        elif "results" in payload:
            pairs = _web_citations(payload)
        else:
            pairs = _document_citations(payload)
        for citation_id, citation in pairs:
            indexed.setdefault(citation_id, citation)
    return [indexed[citation_id] for citation_id in sorted(indexed)]


def citations_from_latest_turn(messages: Iterable[Any]) -> list[dict[str, Any]]:
    """只汇总最后一条用户输入之后的工具证据，避免 checkpoint 旧轮次同号引用串用。"""

    current: list[Any] = []
    for message in messages:
        if isinstance(message, HumanMessage) or (
            isinstance(message, dict)
            and str(message.get("type") or message.get("role") or "").lower() in {"human", "user"}
        ):
            current = []
        else:
            current.append(message)
    return citations_from_messages(current)


def citations_from_tool_message(message: Any) -> list[dict[str, Any]]:
    return citations_from_messages([message])
