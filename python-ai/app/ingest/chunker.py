"""PageBlock → RAG TextChunk（可配置 size / overlap）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ingest.models import PageBlock, TableBlock

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 128
MAX_CHUNK_SIZE = 2000

_HEADER_ONLY_RE = re.compile(
    r"^[\s\d]*(?:[\u4e00-\u9fffA-Za-z（）()·]+)?(?:股份有限公司|有限公司)?\d{4}年年度报告全文\s*$"
)


def _is_header_only_chunk(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return True
    if _HEADER_ONLY_RE.match(normalized):
        return True
    return "年度报告全文" in normalized and len(normalized) < 100


def _table_text(table: TableBlock) -> str:
    markdown = (table.markdown or "").strip()
    if markdown:
        return markdown
    if not table.rows:
        return ""
    return "\n".join(" | ".join(cell.strip() for cell in row if cell) for row in table.rows if any(row))


def _page_indexable_text(block: PageBlock) -> str:
    parts: list[str] = []
    body = block.text.strip()
    if body:
        parts.append(body)
    for table in block.tables:
        table_body = _table_text(table)
        if table_body:
            parts.append(table_body)
    return "\n\n".join(parts)


@dataclass(frozen=True)
class TextChunk:
    doc_id: str
    chunk_index: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_text(text: str, *, chunk_size: int, chunk_overlap: int, max_chunk_size: int) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []
    if len(normalized) <= max_chunk_size:
        if len(normalized) <= chunk_size:
            return [normalized]
        # 单页超长：滑动窗口
        parts: list[str] = []
        step = max(chunk_size - chunk_overlap, 1)
        start = 0
        while start < len(normalized):
            part = normalized[start : start + chunk_size].strip()
            if part:
                parts.append(part)
            if start + chunk_size >= len(normalized):
                break
            start += step
        return parts

    # 超过硬上限仍按窗口切（避免单 chunk 过大）
    parts = []
    step = max(chunk_size - chunk_overlap, 1)
    start = 0
    while start < len(normalized):
        part = normalized[start : start + min(chunk_size, max_chunk_size)].strip()
        if part:
            parts.append(part)
        if start + chunk_size >= len(normalized):
            break
        start += step
    return parts


def chunk_page_blocks(
    blocks: list[PageBlock],
    *,
    doc_id: str,
    source_file: str,
    content_hash: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_chunk_size: int = MAX_CHUNK_SIZE,
) -> list[TextChunk]:
    """按页切分叙述正文；每块 metadata 带 page 供 citation。"""
    chunks: list[TextChunk] = []
    index = 0
    for block in blocks:
        page_text = _page_indexable_text(block)
        parts = _split_text(
            page_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            max_chunk_size=max_chunk_size,
        )
        for part in parts:
            if len(part.strip()) < 20:
                continue
            if _is_header_only_chunk(part):
                continue
            chunks.append(
                TextChunk(
                    doc_id=doc_id,
                    chunk_index=index,
                    content=part,
                    metadata={
                        "source_type": "pdf",
                        "doc_id": doc_id,
                        "page": block.page_no,
                        "page_end": block.page_no,
                        "source_file": source_file,
                        "content_hash": content_hash,
                        "has_table": bool(block.tables),
                    },
                )
            )
            index += 1
    return chunks
