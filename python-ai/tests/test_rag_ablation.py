from contextlib import contextmanager
from unittest.mock import MagicMock

from app.db.chunk_repository import ChunkHit
from app.eval.rag_ablation import compare_ablation_reports, render_markdown
from app.eval.rag_retrieval_runner import (
    citation_accuracy,
    ndcg_at_k,
    page_hit_at_k,
    reciprocal_rank,
    summarize,
)
from app.rag.modes import parse_retrieval_mode, resolve_retrieval_flags
from app.rag.service import retrieve_hits_with_trace


def _hit(chunk_index: int, page: int, text: str, *, vector: float = 0.8, keyword: float | None = None) -> ChunkHit:
    return ChunkHit(
        doc_id="002594_2024",
        chunk_index=chunk_index,
        content=text,
        metadata={"page": page},
        score=vector if keyword is None else keyword,
        vector_score=vector,
        keyword_score=keyword,
    )


SUBSTANTIVE = "本集团二零二四年营业收入四千亿元，研发投入约为五百亿元，较上年明显增长。"


def test_resolve_retrieval_flags_three_modes():
    assert resolve_retrieval_flags("baseline", rerank_enabled=True) == (False, False)
    assert resolve_retrieval_flags("hybrid", rerank_enabled=True) == (True, False)
    assert resolve_retrieval_flags("rerank", rerank_enabled=False) == (True, True)
    assert resolve_retrieval_flags(None, rerank_enabled=True) == (True, True)
    assert resolve_retrieval_flags(None, rerank_enabled=False) == (True, False)


def test_parse_retrieval_mode_accepts_production_alias():
    assert parse_retrieval_mode(None) is None
    assert parse_retrieval_mode("production") is None
    assert parse_retrieval_mode("Rerank") == "rerank"


def test_page_metrics():
    assert page_hit_at_k([137, 10], [10, 11], 12) is True
    assert page_hit_at_k([137, 110], [10], 12) is False
    assert reciprocal_rank([137, 110, 11], [11], 12) == 1 / 3


def test_ndcg_at_k_rewards_rank_and_all_gold_pages():
    assert ndcg_at_k([10, 20], [10], 12) == 1.0
    assert ndcg_at_k([20, 10], [10], 12) == 0.6309
    assert ndcg_at_k([10, 11], [10, 11], 12) == 1.0
    last_two = list(range(1, 11)) + [10, 11]
    first_two = ndcg_at_k([10, 11] + list(range(1, 11)), [10, 11], 12)
    late = ndcg_at_k(last_two, [10, 11], 12)
    assert first_two == 1.0
    assert late < first_two
    assert ndcg_at_k([], [10], 12) == 0.0
    assert ndcg_at_k([10, 10, 11], [10, 11], 12) == 1.0


def test_citation_accuracy_is_page_precision():
    assert citation_accuracy([10, 20, 30], [10], 12) == round(1 / 3, 4)
    assert citation_accuracy([10, 11], [10, 11], 12) == 1.0
    assert citation_accuracy([], [10], 12) == 0.0
    assert citation_accuracy([10, 10, 99], [10], 12) == 0.5


def test_summarize_includes_latency():
    summary = summarize(
        [
            {
                "category": "numeric_financial",
                "page_hit_at_k": True,
                "reciprocal_rank": 1.0,
                "ndcg_at_k": 1.0,
                "citation_accuracy": 1.0,
                "latency_ms": 10,
            },
            {
                "category": "numeric_financial",
                "page_hit_at_k": False,
                "reciprocal_rank": 0.0,
                "ndcg_at_k": 0.0,
                "citation_accuracy": 0.0,
                "latency_ms": 30,
            },
        ]
    )
    assert summary["count"] == 2
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.5
    assert summary["ndcg_at_k"] == 0.5
    assert summary["citation_accuracy"] == 0.5
    assert summary["by_category"]["numeric_financial"]["citation_accuracy"] == 0.5
    assert summary["by_category"]["numeric_financial"]["ndcg_at_k"] == 0.5
    assert summary["latency_p50_ms"] == 20.0
    assert summary["by_category"]["numeric_financial"]["count"] == 2


def _fake_report(mode: str, hits: dict[str, bool], *, recall: float, mrr: float, p50: float) -> dict:
    results = []
    for item_id, hit in hits.items():
        results.append(
            {
                "id": item_id,
                "category": "numeric_financial" if item_id.endswith("1") else "product_enum",
                "question": f"q-{item_id}",
                "gold_pages": [10],
                "retrieved_pages": [10] if hit else [99],
                "page_hit_at_k": hit,
                "reciprocal_rank": 1.0 if hit else 0.0,
            }
        )
    by_category = {
        "numeric_financial": {
            "recall_at_k": 1.0 if hits.get("rag-001") else 0.0,
            "mrr": 1.0 if hits.get("rag-001") else 0.0,
            "ndcg_at_k": 1.0 if hits.get("rag-001") else 0.0,
            "count": 1,
        },
        "product_enum": {
            "recall_at_k": 1.0 if hits.get("rag-002") else 0.0,
            "mrr": 1.0 if hits.get("rag-002") else 0.0,
            "ndcg_at_k": 1.0 if hits.get("rag-002") else 0.0,
            "count": 1,
        },
    }
    return {
        "summary": {
            "count": 2,
            "recall_at_k": recall,
            "mrr": mrr,
            "ndcg_at_k": mrr,
            "latency_p50_ms": p50,
            "latency_p95_ms": p50 + 10,
            "latency_mean_ms": p50,
            "by_category": by_category,
        },
        "results": results,
    }


def test_compare_ablation_adjacent_deltas_and_flips():
    reports = {
        "baseline": _fake_report("baseline", {"rag-001": True, "rag-002": False}, recall=0.5, mrr=0.5, p50=40),
        "hybrid": _fake_report("hybrid", {"rag-001": True, "rag-002": True}, recall=1.0, mrr=1.0, p50=55),
        "rerank": _fake_report("rerank", {"rag-001": False, "rag-002": True}, recall=0.5, mrr=0.5, p50=180),
    }
    diff = compare_ablation_reports(reports)
    hybrid_step = diff["adjacent"][0]
    rerank_step = diff["adjacent"][1]
    assert hybrid_step["from"] == "baseline"
    assert hybrid_step["recall_at_k_delta"] == 0.5
    assert hybrid_step["ndcg_at_k_delta"] == 0.5
    assert len(hybrid_step["improvements"]) == 1
    assert hybrid_step["improvements"][0]["id"] == "rag-002"
    assert rerank_step["recall_at_k_delta"] == -0.5
    assert len(rerank_step["regressions"]) == 1
    assert rerank_step["regressions"][0]["id"] == "rag-001"
    markdown = render_markdown(
        {
            "generated_at": "2026-09-10T00:00:00+00:00",
            "golden_file": "rag_retrieval_100.json",
            "params": {"top_k": 12, "count": 2},
            "summary": diff,
        }
    )
    assert "baseline" in markdown
    assert "相邻 Δ" in markdown
    assert "不必单调上升" in markdown
    assert "分题型 MRR" in markdown
    assert "分题型 nDCG@k" in markdown
    assert "nDCG@k" in markdown
    assert "citation_accuracy" in markdown
    assert hybrid_step["citation_accuracy_delta"] == 0.0


def test_baseline_skips_keyword_and_rerank(monkeypatch):
    vector_hits = [_hit(1, 10, SUBSTANTIVE)]
    keyword_calls: list[int] = []
    rerank_calls: list[int] = []

    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.rag.service.embed_text", lambda _q: [0.1] * 8)
    monkeypatch.setattr("app.rag.service.get_connection", fake_conn)
    monkeypatch.setattr(
        "app.rag.service.search_similar_chunks",
        lambda *_a, **_k: vector_hits,
    )
    monkeypatch.setattr(
        "app.rag.service.search_keyword_chunks",
        lambda *_a, **_k: keyword_calls.append(1) or [_hit(2, 22, SUBSTANTIVE, keyword=2.0)],
    )
    monkeypatch.setattr(
        "app.rag.service.rerank_with_cross_encoder",
        lambda *_a, **_k: rerank_calls.append(1) or vector_hits,
    )

    hits, pipeline = retrieve_hits_with_trace(
        question="比亚迪2024年营业收入是多少",
        doc_ids=["002594_2024"],
        top_k=5,
        mode="baseline",
    )
    assert hits
    assert keyword_calls == []
    assert rerank_calls == []
    assert pipeline["use_keyword"] is False
    assert pipeline["use_rerank"] is False
    assert pipeline["keyword_hit_count"] == 0


def test_hybrid_uses_keyword_but_skips_rerank(monkeypatch):
    vector_hits = [_hit(1, 10, SUBSTANTIVE, vector=0.4)]
    keyword_hits = [_hit(2, 22, SUBSTANTIVE + " 新推出车型", keyword=3.0, vector=0.2)]
    rerank_calls: list[int] = []

    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.rag.service.embed_text", lambda _q: [0.1] * 8)
    monkeypatch.setattr("app.rag.service.get_connection", fake_conn)
    monkeypatch.setattr("app.rag.service.search_similar_chunks", lambda *_a, **_k: vector_hits)
    monkeypatch.setattr("app.rag.service.search_keyword_chunks", lambda *_a, **_k: keyword_hits)
    monkeypatch.setattr(
        "app.rag.service.rerank_with_cross_encoder",
        lambda *_a, **_k: rerank_calls.append(1) or keyword_hits,
    )

    _hits, pipeline = retrieve_hits_with_trace(
        question="2024年长城新推出的车型",
        doc_ids=["601633_2024"],
        top_k=5,
        mode="hybrid",
    )
    assert pipeline["use_keyword"] is True
    assert pipeline["use_rerank"] is False
    assert pipeline["keyword_hit_count"] == 1
    assert rerank_calls == []
    assert "keyword_search" in pipeline["timing_ms"]


def test_rerank_mode_forces_cross_encoder_even_if_setting_off(monkeypatch):
    vector_hits = [_hit(1, 10, SUBSTANTIVE)]
    reranked = [_hit(9, 11, SUBSTANTIVE, vector=0.9)]
    rerank_calls: list[int] = []

    class _Settings:
        rag_vector_fetch_k = 80
        rag_keyword_top_k = 30
        rag_bm25_k1 = 1.2
        rag_bm25_b = 0.75
        rag_rrf_k = 60
        rag_vector_rrf_weight = 2.0
        rag_keyword_rrf_weight = 1.0
        rag_rerank_enabled = False
        rag_rerank_model = "BAAI/bge-reranker-v2-m3"
        rag_rerank_candidates = 80
        rag_max_chunks_per_page = 1
        rag_enum_keyword_rrf_weight = 2.0
        rag_section_title_boost = 3

    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.rag.service.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.rag.service.embed_text", lambda _q: [0.1] * 8)
    monkeypatch.setattr("app.rag.service.get_connection", fake_conn)
    monkeypatch.setattr("app.rag.service.search_similar_chunks", lambda *_a, **_k: vector_hits)
    monkeypatch.setattr("app.rag.service.search_keyword_chunks", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "app.rag.service.rerank_with_cross_encoder",
        lambda *_a, **_k: rerank_calls.append(1) or reranked,
    )

    hits, pipeline = retrieve_hits_with_trace(
        question="比亚迪2024年营业收入是多少",
        doc_ids=["002594_2024"],
        top_k=5,
        mode="rerank",
    )
    assert rerank_calls == [1]
    assert pipeline["use_rerank"] is True
    assert hits[0].chunk_index == 9
    assert "rerank" in pipeline["timing_ms"]
