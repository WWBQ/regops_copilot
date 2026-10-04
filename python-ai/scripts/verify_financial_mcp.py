"""通过 FastMCP 客户端验证工具协议与失败关闭行为；不访问真实数据服务。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mcp import financial_server as financial_mcp
from app.db.chunk_repository import ChunkHit


def _fact(*, year: int = 2024, status: str = "auto_accepted", page: int | None = None, value: str = "123.45", digest: str = "sha256:" + "a" * 64) -> dict:
    return {
        "company_code": "000333", "concept": "revenue", "period": f"{year}-12-31",
        "scope": "consolidated", "status": status, "currency": "CNY",
        "value_yuan": value, "doc_id": f"000333_{year}", "page_no": page,
        "fact_key": f"revenue_{year}", "source_type": "web",
        "parser": "eastmoney_f10", "content_hash": digest,
    }


async def main() -> None:
    async with Client(financial_mcp.mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert {"lookup_financial_facts", "search_report_evidence"} <= tools.keys()
        assert all(tools[name].annotations.read_only_hint is True for name in ("lookup_financial_facts", "search_report_evidence"))

        with patch.object(financial_mcp, "_request_json", return_value={"total": 2, "items": [_fact(), _fact(year=2023, status="human_review")]}) as request:
            result = await client.call_tool("lookup_financial_facts", {"company_code": "000333", "concept": "revenue", "years": [2023, 2024, 2025]})
            assert result.data == {
                "status": "ok", "company_code": "000333", "concept": "revenue",
                "facts": [
                    {"year": 2023, "outcome": "unverified", "review_required": True},
                    {"year": 2024, "outcome": "ok", "value_yuan": "123.45", "currency": "CNY", "scope": "consolidated", "sources": [{"doc_id": "000333_2024", "source_type": "web", "parser": "eastmoney_f10", "content_hash": "sha256:" + "a" * 64, "fact_key": "revenue_2024"}]},
                    {"year": 2025, "outcome": "missing", "review_required": False},
                ],
            }
            assert request.call_args.args == ("GET", "/ops/quality/facts")

        # F10 没有 PDF 页码是正常的；完整哈希和质量门通过才允许初筛使用。
        with patch.object(financial_mcp, "_request_json", return_value={"total": 1, "items": [_fact(page=None)]}):
            result = await client.call_tool("lookup_financial_facts", {"company_code": "000333", "concept": "revenue", "years": [2024]})
            assert result.data["facts"][0]["outcome"] == "ok"
            assert "page" not in result.data["facts"][0]["sources"][0]

        with patch.object(financial_mcp, "_request_json", return_value={"total": 1, "items": [_fact(digest="sha256:short")]}):
            result = await client.call_tool("lookup_financial_facts", {"company_code": "000333", "concept": "revenue", "years": [2024]})
            assert result.data["facts"][0]["outcome"] == "missing_provenance"

        with patch.object(financial_mcp, "_request_json", return_value={"total": 1, "items": [{**_fact(), "source_type": "pdf", "page_no": 12}]}):
            result = await client.call_tool("lookup_financial_facts", {"company_code": "000333", "concept": "revenue", "years": [2024]})
            assert result.data["facts"][0]["outcome"] == "missing"

        with patch.object(financial_mcp, "_request_json", return_value={"total": 2, "items": [_fact(), _fact(value="999")] }):
            result = await client.call_tool("lookup_financial_facts", {"company_code": "000333", "concept": "revenue", "years": [2024]})
            assert result.data["facts"][0]["outcome"] == "conflict"

        with patch.object(financial_mcp, "_request_json", side_effect=RuntimeError("财务数据服务不可访问或请求超时")):
            result = await client.call_tool("lookup_financial_facts", {"company_code": "000333", "concept": "revenue", "years": [2024]})
            assert result.data["status"] == "unavailable"

        with patch.object(financial_mcp, "_request_json", side_effect=AssertionError("invalid input must not call backend")):
            result = await client.call_tool("lookup_financial_facts", {"company_code": "333", "concept": "revenue", "years": [2024]})
            assert result.data["status"] == "invalid_input"

        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        hits = [
            ChunkHit("000333_2024", 1, "营业收入有所增长", {"page": 8}, 0.9),
            ChunkHit("000333_2023", 2, "跨年证据", {"page": 8}, 0.9),
            ChunkHit("000333_2024", 3, "缺页码", {"page": 0}, 0.9),
        ]
        settings = SimpleNamespace(rag_rerank_enabled=True, rag_rerank_backend="bge", rag_min_score=0.42)
        with (
            patch.object(financial_mcp, "get_connection", return_value=conn),
            patch.object(financial_mcp, "get_settings", return_value=settings),
            patch.object(financial_mcp, "retrieve_relevant_hits_for_docs", return_value=(hits, {})) as retrieve,
            patch.object(financial_mcp, "_request_json", side_effect=AssertionError("evidence must not call /chat")),
        ):
            result = await client.call_tool("search_report_evidence", {"company_code": "000333", "year": 2024, "question": "经营重点是什么"})
            assert result.data["status"] == "ok"
            assert result.data["citations"] == [{"doc_id": "000333_2024", "page": 8, "snippet": "营业收入有所增长"}]
            assert retrieve.call_args.kwargs == {
                "question": "经营重点是什么", "doc_ids": ["000333_2024"],
                "top_k": 8, "min_score": 0.42, "mode": "rerank",
            }
            assert cursor.execute.call_args.args[1] == ("000333_2024", "000333", 2024)

        with (
            patch.object(financial_mcp, "get_connection", return_value=conn),
            patch.object(financial_mcp, "get_settings", return_value=SimpleNamespace(rag_rerank_enabled=True, rag_rerank_backend="llm", rag_min_score=0.42)),
            patch.object(financial_mcp, "retrieve_relevant_hits_for_docs", return_value=([], {})) as retrieve,
        ):
            result = await client.call_tool("search_report_evidence", {"company_code": "000333", "year": 2024, "question": "经营重点是什么"})
            assert result.data["status"] == "insufficient_evidence"
            assert retrieve.call_args.kwargs["mode"] == "hybrid"

        cursor.fetchone.return_value = None
        with (
            patch.object(financial_mcp, "get_connection", return_value=conn),
            patch.object(financial_mcp, "retrieve_relevant_hits_for_docs", side_effect=AssertionError("missing report must not retrieve")),
        ):
            result = await client.call_tool("search_report_evidence", {"company_code": "000333", "year": 2025, "question": "经营重点是什么"})
            assert result.data["status"] == "insufficient_evidence"

    # HTTP 配置和请求头不进入模型输出；禁止跟随服务端重定向。
    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"ok": True}

    with (
        patch.object(financial_mcp, "get_settings", return_value=type("Settings", (), {"service_token": "secret", "regops_api_base_url": "http://127.0.0.1:8000"})()),
        patch.object(financial_mcp.requests, "request", return_value=FakeResponse()) as request,
    ):
        assert financial_mcp._request_json("GET", "/ops/quality/facts") == {"ok": True}
        assert request.call_args.kwargs["allow_redirects"] is False
        assert request.call_args.kwargs["headers"] == {"X-Regops-Service-Token": "secret"}

    print("financial MCP verification passed")


if __name__ == "__main__":
    asyncio.run(main())
