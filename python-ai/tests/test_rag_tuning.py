from app.eval.rag_tuning import select_candidate


def test_tuning_prefers_faster_candidate_inside_quality_band():
    rows = [
        {
            "rerank_candidates": 12,
            "recall_at_k": 0.90,
            "ndcg_at_k": 0.80,
            "latency_p50_ms": 100,
            "latency_p95_ms": 150,
            "rerank_fallback_count": 0,
        },
        {
            "rerank_candidates": 24,
            "recall_at_k": 0.91,
            "ndcg_at_k": 0.81,
            "latency_p50_ms": 180,
            "latency_p95_ms": 260,
            "rerank_fallback_count": 0,
        },
    ]
    assert select_candidate(rows)["rerank_candidates"] == 12


def test_tuning_rejects_fast_candidate_outside_quality_band():
    rows = [
        {
            "rerank_candidates": 12,
            "recall_at_k": 0.85,
            "ndcg_at_k": 0.70,
            "latency_p50_ms": 80,
            "latency_p95_ms": 100,
            "rerank_fallback_count": 0,
        },
        {
            "rerank_candidates": 24,
            "recall_at_k": 0.91,
            "ndcg_at_k": 0.81,
            "latency_p50_ms": 180,
            "latency_p95_ms": 260,
            "rerank_fallback_count": 0,
        },
    ]
    assert select_candidate(rows)["rerank_candidates"] == 24
