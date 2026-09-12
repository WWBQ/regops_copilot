"""Okapi BM25（Lucene 正 IDF）。

词项来自问题抽取的短语 / 代码（与 `extract_keyword_terms` 同一套），
文档侧用大小写不敏感的子串次数当 TF。这样中文科目名不必依赖分词器，
同时具备真 BM25 的 TF 饱和、IDF 和长度归一，而不是 ILIKE 二进制打分。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def lucene_idf(n_docs: int, df: int) -> float:
    """IDF = ln(1 + (N - df + 0.5) / (df + 0.5))，恒为正。"""
    if n_docs <= 0 or df <= 0:
        return 0.0
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def okapi_tf(tf: float, dl: float, avgdl: float, *, k1: float, b: float) -> float:
    if tf <= 0 or k1 <= 0:
        return 0.0
    denom_avg = avgdl if avgdl > 0 else 1.0
    length_norm = 1.0 - b + b * (dl / denom_avg)
    return (tf * (k1 + 1.0)) / (tf + k1 * length_norm)


def term_tf(text: str, term: str) -> int:
    if not text or not term:
        return 0
    return text.casefold().count(term.casefold())


@dataclass(frozen=True)
class Bm25Stats:
    n_docs: int
    avgdl: float
    df: dict[str, int]
    k1: float
    b: float


def build_stats(
    texts: list[str],
    terms: list[str],
    *,
    k1: float = 1.2,
    b: float = 0.75,
) -> Bm25Stats:
    n_docs = len(texts)
    if n_docs == 0:
        return Bm25Stats(n_docs=0, avgdl=1.0, df={}, k1=k1, b=b)
    avgdl = sum(max(len(text), 1) for text in texts) / n_docs
    df = {term: sum(1 for text in texts if term_tf(text, term) > 0) for term in terms}
    return Bm25Stats(n_docs=n_docs, avgdl=avgdl, df=df, k1=k1, b=b)


def score_text(text: str, terms: list[str], stats: Bm25Stats) -> float:
    if stats.n_docs <= 0 or not terms:
        return 0.0
    dl = max(len(text), 1)
    score = 0.0
    for term in terms:
        tf = term_tf(text, term)
        if tf <= 0:
            continue
        score += lucene_idf(stats.n_docs, stats.df.get(term, 0)) * okapi_tf(
            tf, dl, stats.avgdl, k1=stats.k1, b=stats.b
        )
    return score
