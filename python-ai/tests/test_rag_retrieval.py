from app.db.chunk_repository import ChunkHit
from app.rag.retrieval import (
    apply_page_diversity,
    apply_section_title_boost,
    extract_keyword_terms,
    filter_substantive_hits,
    hit_passes_relevance_threshold,
    is_enumeration_question,
    is_low_value_chunk,
    merge_session_first,
    reciprocal_rank_fusion,
)


def test_is_low_value_chunk_detects_annual_header():
    assert is_low_value_chunk("比亚迪股份有限公司2024年年度报告全文") is True
    assert is_low_value_chunk("  002594  比亚迪股份有限公司2024年年度报告全文  ") is True


def test_is_low_value_chunk_keeps_substantive_text():
    text = "二零二四年研发投入约为542亿元，同比上升35.68%"
    assert is_low_value_chunk(text) is False


def test_is_low_value_chunk_keeps_short_section_title():
    assert is_low_value_chunk("本集团 2024 年新推出的车型") is False
    assert is_low_value_chunk("短句。") is True


def test_filter_substantive_hits_removes_headers():
    hits = [
        ChunkHit("002594_2024", 1, "比亚迪股份有限公司2024年年度报告全文", {"page": 80}, 0.76),
        ChunkHit(
            "002594_2024",
            24,
            "本集团二零二四年研发投入约为542亿元，同比上升35.68%",
            {"page": 14},
            0.53,
        ),
    ]
    filtered = filter_substantive_hits(hits, top_k=5)
    assert len(filtered) == 1
    assert filtered[0].chunk_index == 24


def test_extract_keyword_terms_from_question_only():
    terms = extract_keyword_terms("比亚迪2024年研发投入是多少")
    assert "比亚迪研发投入" in terms
    assert "研发投入" in terms
    assert "2024" not in terms
    assert "研发费用" not in terms


def test_extract_keyword_terms_splits_vehicle_question():
    terms = extract_keyword_terms("2024年长城新推出的车型")
    assert "2024" not in terms
    assert any("长城" in term for term in terms)
    assert "车型" in terms
    assert "哈弗" not in terms
    # 不再注入行业同义词，只保留问句里出现过的词
    assert "上市" not in terms
    assert "发布" not in terms


def test_is_enumeration_question_uses_phrasing_not_industry_words():
    assert is_enumeration_question("格力电器2024年推出了哪些新产品") is True
    assert is_enumeration_question("三一重工2024年推出了哪些新机型或新产品") is True
    assert is_enumeration_question("2024年长城新推出的车型有哪些") is True
    assert is_enumeration_question("比亚迪2024年营业收入是多少") is False
    assert is_enumeration_question("比亚迪2024年新能源汽车销量是多少") is False


def test_apply_section_title_boost_promotes_matching_section():
    hits = [
        ChunkHit("d1", 1, "a", {"page": 19, "section_title": "出海与全球化战略"}, 0.9),
        ChunkHit("d1", 2, "b", {"page": 20, "section_title": "出海与全球化战略"}, 0.85),
        ChunkHit("d1", 3, "c", {"page": 21, "section_title": "出海与全球化战略"}, 0.8),
        ChunkHit("d1", 4, "d", {"page": 22, "section_title": "本集团2024年新推出的车型"}, 0.7),
    ]
    boosted = apply_section_title_boost(hits, ["车型", "长城"], promote=3)
    assert [hit.chunk_index for hit in boosted] == [4, 1, 2, 3]


def test_apply_section_title_boost_is_noop_when_disabled_or_unmatched():
    hits = [
        ChunkHit("d1", 1, "a", {"page": 19, "section_title": "出海战略"}, 0.9),
        ChunkHit("d1", 2, "b", {"page": 22, "section_title": "新推出的车型"}, 0.7),
    ]
    assert apply_section_title_boost(hits, ["车型"], promote=0) == hits
    assert apply_section_title_boost(hits, [], promote=3) == hits
    assert apply_section_title_boost(hits, ["研发投入"], promote=3) == hits


def test_reciprocal_rank_fusion_promotes_dual_matches():
    vector_hits = [
        ChunkHit("d1", 1, "header noise", {}, 0.9),
        ChunkHit("d1", 2, "answer chunk", {}, 0.55),
    ]
    keyword_hits = [
        ChunkHit("d1", 2, "answer chunk", {}, 2.0),
        ChunkHit("d1", 3, "keyword only", {}, 1.5),
    ]
    fused = reciprocal_rank_fusion(vector_hits, keyword_hits, k=60)
    assert fused[0].chunk_index == 2
    assert fused[0].vector_score == 0.55
    assert fused[0].keyword_score == 2.0


def test_apply_page_diversity_limits_same_page():
    hits = [
        ChunkHit("d1", 1, "a", {"page": 20}, 0.9),
        ChunkHit("d1", 2, "b", {"page": 20}, 0.85),
        ChunkHit("d1", 3, "c", {"page": 20}, 0.8),
        ChunkHit("d1", 4, "d", {"page": 22}, 0.75),
    ]
    picked = apply_page_diversity(hits, top_k=3, max_per_page=1)
    pages = [h.metadata["page"] for h in picked]
    assert pages.count(20) == 1
    assert 22 in pages


def test_apply_page_diversity_unlimited_keeps_same_page():
    hits = [
        ChunkHit("d1", 1, "a", {"page": 20}, 0.9),
        ChunkHit("d1", 2, "b", {"page": 20}, 0.85),
        ChunkHit("d1", 3, "c", {"page": 20}, 0.8),
        ChunkHit("d1", 4, "d", {"page": 22}, 0.75),
    ]
    picked = apply_page_diversity(hits, top_k=3, max_per_page=0)
    assert [h.chunk_index for h in picked] == [1, 2, 3]


def test_apply_page_diversity_keeps_two_per_page():
    hits = [
        ChunkHit("d1", 1, "a", {"page": 20}, 0.9),
        ChunkHit("d1", 2, "b", {"page": 20}, 0.85),
        ChunkHit("d1", 3, "c", {"page": 20}, 0.8),
        ChunkHit("d1", 4, "d", {"page": 22}, 0.75),
    ]
    picked = apply_page_diversity(hits, top_k=3, max_per_page=2)
    assert [h.chunk_index for h in picked] == [1, 2, 4]
    pages = [h.metadata["page"] for h in picked]
    assert pages.count(20) == 2
    assert 22 in pages


def test_merge_session_first_keeps_upload_ahead_of_corpus():
    session = [
        ChunkHit("sess_a", 1, "upload", {"page": 1}, 0.4),
        ChunkHit("sess_a", 2, "upload-2", {"page": 2}, 0.3),
    ]
    corpus = [
        ChunkHit("002594_2024", 9, "annual", {"page": 9}, 0.99),
        ChunkHit("002594_2024", 10, "annual-2", {"page": 10}, 0.98),
        ChunkHit("002594_2024", 11, "annual-3", {"page": 11}, 0.97),
    ]
    merged = merge_session_first(session, corpus, top_k=3)
    assert [hit.doc_id for hit in merged] == ["sess_a", "sess_a", "002594_2024"]
    assert merged[2].chunk_index == 9


def test_hit_passes_relevance_threshold_with_hybrid_scores():
    vector_only = ChunkHit("d1", 1, "x", {}, 0.02, vector_score=0.5, keyword_score=None)
    keyword_only = ChunkHit("d1", 2, "x", {}, 0.02, vector_score=None, keyword_score=1.0)
    weak = ChunkHit("d1", 3, "x", {}, 0.01, vector_score=0.2, keyword_score=None)
    assert hit_passes_relevance_threshold(vector_only, 0.42) is True
    assert hit_passes_relevance_threshold(keyword_only, 0.42) is True
    assert hit_passes_relevance_threshold(weak, 0.42) is False
