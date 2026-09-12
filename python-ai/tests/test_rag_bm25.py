from app.db.chunk_repository import search_keyword_chunks
from app.rag.bm25 import build_stats, lucene_idf, okapi_tf, score_text, term_tf


def _pad(text: str) -> str:
    return text + "。本段为年报正文摘录，用于满足检索噪声过滤长度。"


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchall(self):
        return self.rows


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _FakeCursor(self.rows)


def test_lucene_idf_rarer_term_scores_higher():
    rare = lucene_idf(100, 2)
    common = lucene_idf(100, 80)
    assert rare > common > 0


def test_okapi_tf_saturates_and_penalizes_length():
    once_short = okapi_tf(1, 40, 80, k1=1.2, b=0.75)
    many_short = okapi_tf(8, 40, 80, k1=1.2, b=0.75)
    once_long = okapi_tf(1, 400, 80, k1=1.2, b=0.75)
    assert many_short > once_short
    assert once_short > once_long
    extra = okapi_tf(40, 40, 80, k1=1.2, b=0.75)
    assert extra / many_short < 8 / 1


def test_term_tf_is_case_insensitive_count():
    assert term_tf("Revenue revenue REVENUE", "revenue") == 3
    assert term_tf("营业收入与营业总收入", "营业收入") == 1


def test_score_text_prefers_dense_short_hit():
    terms = ["氢能"]
    dense = _pad("氢能业务氢能规划")
    padded = _pad("氢能业务。" + "其他说明" * 40)
    other = _pad("营业收入一百亿元")
    stats = build_stats([dense, padded, other], terms)
    assert score_text(dense, terms, stats) > score_text(padded, terms, stats)
    assert score_text(other, terms, stats) == 0


def test_search_keyword_chunks_ranks_by_bm25_and_drops_headers():
    header = "比亚迪股份有限公司2024年年度报告全文"
    revenue_once = _pad("本集团营业收入一百亿元")
    revenue_many = _pad("营业收入、营业收入、营业收入合计")
    hydrogen = _pad("本集团氢能业务规划")
    conn = _FakeConn(
        [
            ("002594_2024", 1, header, {"page": 1}),
            ("002594_2024", 2, revenue_once, {"page": 10}),
            ("002594_2024", 3, revenue_many, {"page": 11}),
            ("002594_2024", 4, hydrogen, {"page": 80}),
        ]
    )
    hits = search_keyword_chunks(conn, ["002594_2024"], ["营业收入"], top_k=5)
    assert [hit.chunk_index for hit in hits] == [3, 2]
    assert hits[0].keyword_score > hits[1].keyword_score
    assert hits[0].score == hits[0].keyword_score

    mixed = search_keyword_chunks(conn, ["002594_2024"], ["氢能", "营业收入"], top_k=5)
    assert mixed[0].chunk_index == 4
    assert mixed[0].keyword_score > 0
