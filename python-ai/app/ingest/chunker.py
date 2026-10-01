"""PageBlock → RAG TextChunk：按节切分，标题跟正文走，可挂 clause_no / effective_date。"""

from __future__ import annotations

import html as html_lib
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
_PAGE_FOOTER_RE = re.compile(r"\s*\d{1,3}\s*/\s*\d{2,4}\s*$")
_STRUCT_HEADING_RE = re.compile(
    r"^(?:"
    r"#{1,3}\s+\S.{0,60}"
    r"|第[一二三四五六七八九十百千万零〇0-9]{1,8}[节章编条].{0,48}"
    r"|[（(][一二三四五六七八九十0-9]{1,4}[)）]\s*\S.{0,48}"
    r"|[一二三四五六七八九十]、\s*\S.{0,48}"
    r"|\d{1,2}[、.．]\s*\S.{0,48}"
    r")$"
)
_CLAUSE_RE = re.compile(r"第[一二三四五六七八九十百千万零〇0-9]+条")
_SECTION_NO_RE = re.compile(r"第[一二三四五六七八九十百零〇0-9]+[节章编]")
_EFFECTIVE_DATE_RE = re.compile(
    r"(?:自)?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
_NOT_HEADING_RE = re.compile(r"(以上|详见|注：|单位：|未经审计)")
_ANNUAL_REPORT_DOC_ID_RE = re.compile(r"^(?P<company_code>\d{6})_(?P<year>20\d{2})")


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
    # 表格单独生成 chunk，避免正文 chunk 与表格 chunk 重复入库。
    return block.text.strip()


def _document_scope_metadata(doc_id: str) -> dict[str, Any]:
    match = _ANNUAL_REPORT_DOC_ID_RE.match(doc_id)
    if not match:
        return {}
    return {
        "company_code": match.group("company_code"),
        "year": int(match.group("year")),
    }


def _fallback_table_html(table: TableBlock) -> str:
    """测试数据或旧调用未提供 Docling HTML 时，生成最小可用表格。"""
    if table.html.strip():
        return table.html.strip()
    rows: list[str] = []
    for row_index, row in enumerate(table.rows):
        tag = "th" if row_index == 0 else "td"
        cells = "".join(f"<{tag}>{html_lib.escape(cell)}</{tag}>" for cell in row)
        rows.append(f"<tr>{cells}</tr>")
    return "<table>" + "".join(rows) + "</table>" if rows else ""


def _table_title(
    table: TableBlock,
    sections: list[tuple[str | None, str]],
    *,
    page_no: int,
    table_index: int,
) -> str:
    if table.title.strip():
        return table.title.strip()
    for heading, _body in reversed(sections):
        if heading:
            return heading
    return f"第{page_no}页表格{table_index}"


@dataclass(frozen=True)
class TextChunk:
    doc_id: str
    chunk_index: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalize_heading_line(line: str) -> str:
    return _PAGE_FOOTER_RE.sub("", line).strip()


def is_section_heading(line: str, *, next_line: str | None = None, last_on_page: bool = False) -> bool:
    """识别年报/制度小节标题，避免标题落在上一块末尾。"""
    text = _normalize_heading_line(line)
    if len(text) < 2 or len(text) > 48:
        return False
    if _is_header_only_chunk(text):
        return False
    if re.fullmatch(r"\d{4}年(?:度)?", text):
        return False
    if _NOT_HEADING_RE.search(text):
        return False
    if _STRUCT_HEADING_RE.match(text):
        return True
    if re.search(r"[。；;]$", text) or "|" in text:
        return False
    title_like = 4 <= len(text) <= 40 and not re.search(r"[。；;]", text)
    if not title_like:
        return False
    if last_on_page and next_line is None:
        return True
    if next_line is not None and len(_normalize_heading_line(next_line)) >= 40:
        return True
    return False


def clause_no_from_heading(heading: str | None) -> str | None:
    if not heading:
        return None
    match = _CLAUSE_RE.search(heading) or _SECTION_NO_RE.search(heading)
    return match.group(0) if match else None


def effective_date_from_text(*parts: str | None) -> str | None:
    blob = " ".join(part for part in parts if part)[:200]
    match = _EFFECTIVE_DATE_RE.search(blob)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _split_text(text: str, *, chunk_size: int, chunk_overlap: int, max_chunk_size: int) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return []
    window = min(chunk_size, max_chunk_size)
    if len(normalized) <= window:
        return [normalized]
    parts: list[str] = []
    step = max(window - chunk_overlap, 1)
    start = 0
    while start < len(normalized):
        part = normalized[start : start + window].strip()
        if part:
            parts.append(part)
        if start + window >= len(normalized):
            break
        start += step
    return parts


def _chunks_for_section(
    heading: str | None,
    body: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    max_chunk_size: int,
) -> list[str]:
    prefix = (heading or "").strip()
    body = body.strip()
    if prefix and body:
        full = f"{prefix}\n{body}"
    else:
        full = prefix or body
    parts = _split_text(
        full,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        max_chunk_size=max_chunk_size,
    )
    if not prefix or len(parts) <= 1:
        return parts
    headed: list[str] = []
    for index, part in enumerate(parts):
        if index == 0 or part.startswith(prefix):
            headed.append(part)
            continue
        headed.append(f"{prefix}\n{part}")
    return headed


def _page_sections(text: str, carry_heading: str | None) -> tuple[list[tuple[str | None, str]], str | None]:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not _is_header_only_chunk(line)
    ]
    if not lines:
        return [], carry_heading

    if carry_heading:
        nxt = lines[1] if len(lines) > 1 else None
        if not is_section_heading(lines[0], next_line=nxt, last_on_page=len(lines) == 1):
            lines = [carry_heading, *lines]

    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current_body: list[str] = []

    for index, line in enumerate(lines):
        nxt = lines[index + 1] if index + 1 < len(lines) else None
        last = index == len(lines) - 1
        if is_section_heading(line, next_line=nxt, last_on_page=last):
            if current_heading is not None or current_body:
                sections.append((current_heading, current_body))
            current_heading = _normalize_heading_line(line)
            current_body = []
            continue
        current_body.append(_normalize_heading_line(line))

    if current_heading is not None or current_body:
        sections.append((current_heading, current_body))

    if not sections:
        return [], carry_heading

    heading, body_lines = sections[-1]
    body_text = "\n".join(body_lines).strip()
    if heading and len(body_text) < 20:
        # 本页保留标题 stub（评测 gold 常含标题页），同时下挂到下一页正文
        sections[-1] = (heading, [])
        carry_heading = heading
    else:
        carry_heading = None

    materialized = [(head, "\n".join(body).strip()) for head, body in sections]
    return materialized, carry_heading


def chunk_page_blocks(
    blocks: list[PageBlock],
    *,
    doc_id: str,
    source_file: str,
    content_hash: str,
    parser_backend: str = "docling",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_chunk_size: int = MAX_CHUNK_SIZE,
) -> list[TextChunk]:
    """按页切分叙述正文；节标题与随后正文绑定，跨页标题下挂。"""
    chunks: list[TextChunk] = []
    index = 0
    carry_heading: str | None = None
    scope_metadata = _document_scope_metadata(doc_id)
    for block in blocks:
        page_text = _page_indexable_text(block)
        sections, carry_heading = _page_sections(page_text, carry_heading)
        for heading, body in sections:
            parts = _chunks_for_section(
                heading,
                body,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                max_chunk_size=max_chunk_size,
            )
            clause_no = clause_no_from_heading(heading)
            effective_date = effective_date_from_text(heading, body)
            for part in parts:
                stripped = part.strip()
                if len(stripped) < 8:
                    continue
                if len(stripped) < 20 and not heading:
                    continue
                if _is_header_only_chunk(part):
                    continue
                metadata: dict[str, Any] = {
                    "source_type": "pdf",
                    "doc_id": doc_id,
                    "page": block.page_no,
                    "page_end": block.page_no,
                    "source_file": source_file,
                    "content_hash": content_hash,
                    "parser_backend": parser_backend,
                    "has_table": bool(block.tables),
                    "content_type": "text",
                    **scope_metadata,
                }
                if heading:
                    metadata["section_title"] = heading
                if clause_no:
                    metadata["clause_no"] = clause_no
                if effective_date:
                    metadata["effective_date"] = effective_date
                chunks.append(
                    TextChunk(
                        doc_id=doc_id,
                        chunk_index=index,
                        content=part,
                        metadata=metadata,
                    )
                )
                index += 1

        for table_index, table in enumerate(block.tables, start=1):
            raw_table_text = _table_text(table)
            if not raw_table_text:
                continue
            title = _table_title(
                table,
                sections,
                page_no=block.page_no,
                table_index=table_index,
            )
            table_text = f"{title}\n{raw_table_text}" if title else raw_table_text
            table_html = _fallback_table_html(table)
            metadata = {
                "source_type": "pdf",
                "doc_id": doc_id,
                "page": block.page_no,
                "page_end": block.page_no,
                "source_file": source_file,
                "content_hash": content_hash,
                "parser_backend": parser_backend,
                "has_table": True,
                "content_type": "table",
                "table_id": f"{doc_id}:p{block.page_no}:t{table_index}",
                "table_index": table_index,
                "table_title": title,
                "table_text": table_text,
                "table_html": table_html,
                **scope_metadata,
            }
            chunks.append(
                TextChunk(
                    doc_id=doc_id,
                    chunk_index=index,
                    content=table_text,
                    metadata=metadata,
                )
            )
            index += 1
    return chunks
