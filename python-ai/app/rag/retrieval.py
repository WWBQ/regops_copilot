"""RAG 检索辅助：噪声过滤、问题词抽取、Hybrid 结果融合（RRF）。"""

from __future__ import annotations

import re

from app.db.chunk_repository import ChunkHit

# 年报 PDF 每页重复的页眉/页脚（入库/检索阶段过滤，属于数据质量而非业务规则）
_ANNUAL_HEADER_RE = re.compile(
    r"^[\s\d]*(?:[\u4e00-\u9fffA-Za-z（）()·]+)?(?:股份有限公司|有限公司)?\d{4}年年度报告全文\s*$"
)

# 通用中文停用词（语言学层面，非行业词表）
_STOPWORDS = frozenset(
    {
        "什么",
        "哪些",
        "哪个",
        "多少",
        "几个",
        "是否",
        "怎么",
        "如何",
        "为什么",
        "请问",
        "介绍",
        "一下",
        "公司",
        "企业",
        "集团",
        "股份",
        "有限",
        "年报",
        "报告",
        "全文",
        "文档",
        "信息",
        "相关",
        "具体",
        "详细",
        "简要",
        "总结",
        "查询",
        "告诉",
        "帮我",
        "我们",
        "你们",
        "他们",
        "这个",
        "那个",
        "可以",
        "能不能",
        "有没有",
    }
)


def is_low_value_chunk(content: str) -> bool:
    text = content.strip()
    if not text:
        return True
    if len(text) < 12:
        return True
    if len(text) < 25:
        # 短节标题 stub（跨页标题页）允许进检索；纯页眉仍走下面的年报头规则
        if re.search(r"[。；;]", text) or "|" in text or "年度报告全文" in text:
            return True
    if _ANNUAL_HEADER_RE.match(text):
        return True
    if "年度报告全文" in text and len(text) < 100:
        return True
    return False


def _decompose_chinese_phrase(phrase: str) -> list[str]:
    """较长中文短语拆成子词，便于关键词 OR 命中（不依赖行业词表）。"""
    phrase = phrase.strip()
    if len(phrase) < 4:
        return [phrase] if phrase else []
    parts = [phrase]
    for size in (4, 3, 2):
        if len(phrase) >= size:
            parts.append(phrase[:size])
            parts.append(phrase[-size:])
    return list(dict.fromkeys(parts))


# 列举句式：靠问法判断，不用行业词表（「车型/新品」那种只覆盖车企）
_ENUM_RE = re.compile(r"哪些|哪几|列举|分别是|包括|清单")


def is_enumeration_question(question: str) -> bool:
    """问句是否在要一份清单。用于抬高关键词权重，不改变召回集合。"""
    return bool(_ENUM_RE.search(question or ""))


def extract_keyword_terms(question: str) -> list[str]:
    """从用户问题抽取检索词。只取问句里出现的词，不注入品牌/车名/同义词。"""
    normalized = re.sub(r"(\d+)\s+年", r"\1年", question.strip())
    normalized = re.sub(r"024年", "2024年", normalized)

    terms: list[str] = []
    terms.extend(re.findall(r"\b\d{6}\b", normalized))
    terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", normalized))
    terms.extend(re.findall(r"第[一二三四五六七八九十百]+节", normalized))

    chinese_text = re.sub(r"20\d{2}年?", " ", normalized)
    chinese_text = re.sub(r"[\d\s]+", "", chinese_text)
    chinese_text = re.sub(r"[吗呢啊呀]$", "", chinese_text)
    chinese_text = re.sub(r"(是多少|有多少|怎么样|如何)$", "", chinese_text)

    if chinese_text:
        if len(chinese_text) >= 2 and chinese_text not in _STOPWORDS:
            terms.append(chinese_text)
        for segment in filter(None, chinese_text.split("的")):
            segment = segment.strip()
            if len(segment) >= 2 and segment not in _STOPWORDS:
                terms.append(segment)
                terms.extend(_decompose_chinese_phrase(segment))

    # 年份走 doc 元数据过滤，不参与关键词（否则几乎每段都命中）
    deduped = list(dict.fromkeys(terms))
    return [term for term in deduped if not re.fullmatch(r"20\d{2}", term)][:12]


def reciprocal_rank_fusion(
    *ranked_lists: list[ChunkHit],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[ChunkHit]:
    """RRF：融合多路召回排名（向量 + 关键词/BM25），企业 Hybrid Search 常用做法。"""
    if not ranked_lists:
        return []
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights length must match ranked_lists")

    fused_scores: dict[tuple[str, int], float] = {}
    best_hits: dict[tuple[str, int], ChunkHit] = {}
    vector_scores: dict[tuple[str, int], float] = {}
    keyword_scores: dict[tuple[str, int], float] = {}

    for list_index, (ranked, weight) in enumerate(zip(ranked_lists, weights, strict=True)):
        for rank, hit in enumerate(ranked, start=1):
            key = (hit.doc_id, hit.chunk_index)
            fused_scores[key] = fused_scores.get(key, 0.0) + weight * (1.0 / (k + rank))
            if key not in best_hits:
                best_hits[key] = hit
            if list_index == 0:
                vector_scores[key] = max(vector_scores.get(key, 0.0), hit.score)
            else:
                keyword_scores[key] = max(keyword_scores.get(key, 0.0), hit.score)

    ordered_keys = sorted(fused_scores.keys(), key=lambda key: fused_scores[key], reverse=True)
    fused: list[ChunkHit] = []
    for key in ordered_keys:
        base = best_hits[key]
        fused.append(
            ChunkHit(
                doc_id=base.doc_id,
                chunk_index=base.chunk_index,
                content=base.content,
                metadata=base.metadata,
                score=fused_scores[key],
                vector_score=vector_scores.get(key),
                keyword_score=keyword_scores.get(key),
            )
        )
    return fused


def apply_section_title_boost(
    hits: list[ChunkHit],
    terms: list[str],
    *,
    promote: int,
) -> list[ChunkHit]:
    """section_title 命中查询词的 chunk 提前 promote 名。

    按名次调整而不是加分：RRF 分与 Cross-Encoder 分不同量纲，直接加权会破坏排序。
    稳定排序，未命中的相对次序不变。
    """
    if promote <= 0 or not terms or not hits:
        return hits

    candidates = [term for term in terms if len(term) >= 2]
    if not candidates:
        return hits

    def sort_key(item: tuple[int, ChunkHit]) -> tuple[int, int, int]:
        index, hit = item
        title = str(hit.metadata.get("section_title") or "")
        matched = bool(title) and any(term in title for term in candidates)
        # 名次相同时命中节标题的排前面，否则「提前 N 名」会被原次序抵消
        return (index - promote if matched else index, 0 if matched else 1, index)

    return [hit for _, hit in sorted(enumerate(hits), key=sort_key)]


def apply_page_diversity(
    hits: list[ChunkHit],
    *,
    top_k: int,
    max_per_page: int = 0,
) -> list[ChunkHit]:
    """精排后按页截断。max_per_page<=0 表示同页不限制，只截到 top_k。"""
    if max_per_page <= 0 or top_k <= 0:
        return hits[:top_k]

    selected: list[ChunkHit] = []
    page_counts: dict[int, int] = {}

    for hit in hits:
        if len(selected) >= top_k:
            break
        page = int(hit.metadata.get("page") or 0)
        if page and page_counts.get(page, 0) >= max_per_page:
            continue
        selected.append(hit)
        if page:
            page_counts[page] = page_counts.get(page, 0) + 1

    return selected


def merge_session_first(
    session_hits: list[ChunkHit],
    corpus_hits: list[ChunkHit],
    *,
    top_k: int,
) -> list[ChunkHit]:
    """先放会话上传的切块，再用年报补满 top_k。两套结果不抢同一套名额。"""
    if top_k <= 0:
        return []
    merged: list[ChunkHit] = []
    seen: set[tuple[str, int]] = set()
    for hit in list(session_hits) + list(corpus_hits):
        key = (hit.doc_id, hit.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
        if len(merged) >= top_k:
            break
    return merged


def filter_substantive_hits(hits: list[ChunkHit], *, top_k: int | None = None) -> list[ChunkHit]:
    substantive = [hit for hit in hits if not is_low_value_chunk(hit.content)]
    if top_k is None:
        return substantive
    return substantive[:top_k]


def hit_passes_relevance_threshold(hit: ChunkHit, min_score: float) -> bool:
    """Hybrid / 精排后：向量 cosine 或关键词命中达标即视为相关。"""
    if hit.vector_score is not None and hit.vector_score >= min_score:
        return True
    if hit.keyword_score is not None and hit.keyword_score > 0:
        return True
    if hit.vector_score is None and hit.keyword_score is None:
        return hit.score >= min_score
    return False
