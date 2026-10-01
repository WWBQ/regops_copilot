"""MinerU 4.x 结构化结果 → 项目统一 PageBlock。"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.ingest.models import BBox, PageBlock, TableBlock, TableCellBlock

logger = logging.getLogger(__name__)

_SPACE_RE = re.compile(r"\s+")
_SKIPPED_TEXT_TYPES = frozenset(
    {
        "table",
        "image",
        "chart",
        "header",
        "footer",
        "page_header",
        "page_footer",
        "page_number",
    }
)


class _TableRowsParser(HTMLParser):
    """只提取检索用行列文本；原始 rowspan/colspan 仍保留在 HTML 中。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_is_header = False
        self.header_positions: set[tuple[int, int]] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            if self._row is None:
                self._row = []
            self._cell_parts = []
            self._cell_is_header = tag == "th"
        elif tag == "br" and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell_parts is not None and self._row is not None:
            text = _SPACE_RE.sub(" ", "".join(self._cell_parts)).strip()
            col_index = len(self._row)
            self._row.append(text)
            if self._cell_is_header:
                self.header_positions.add((len(self.rows), col_index))
            self._cell_parts = None
            self._cell_is_header = False
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self.rows.append(self._row)
            self._row = None


def _load_mineru_parse() -> Callable[..., Any]:
    try:
        from mineru.parser import parse
    except ImportError as exc:
        raise RuntimeError(
            "MinerU 未安装；请在 python-ai 虚拟环境执行 "
            "pip install -r requirements-mineru.txt"
        ) from exc
    return parse


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(part for item in value if (part := _text_value(item)))
    if not isinstance(value, dict):
        return ""
    for key in (
        "text",
        "title_content",
        "paragraph_content",
        "list_content",
        "code_content",
        "math_content",
        "content",
    ):
        if key in value and (text := _text_value(value[key])):
            return text
    return ""


def _block_text(block: dict[str, Any]) -> str:
    for key in ("content", "text"):
        if key in block and (text := _text_value(block[key])):
            return text
    return ""


def _table_html(block: dict[str, Any]) -> str:
    content = block.get("content")
    candidates: list[Any] = [block.get("table_body"), block.get("html")]
    if isinstance(content, dict):
        candidates = [content.get("html"), content.get("table_body"), *candidates]
    elif isinstance(content, str) and "<table" in content.lower():
        candidates.insert(0, content)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _table_title(block: dict[str, Any]) -> str:
    content = block.get("content")
    candidates: list[Any] = [block.get("table_caption"), block.get("title")]
    if isinstance(content, dict):
        candidates = [content.get("table_caption"), content.get("title"), *candidates]
    for candidate in candidates:
        if text := _text_value(candidate):
            return _SPACE_RE.sub(" ", text).strip()
    return ""


def _bbox(raw: Any) -> BBox | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return None


def _table_block(block: dict[str, Any], *, page_no: int) -> TableBlock:
    table_html = _table_html(block)
    html_parser = _TableRowsParser()
    if table_html:
        html_parser.feed(table_html)
        html_parser.close()
    rows = html_parser.rows
    cells = [
        TableCellBlock(
            text=text,
            row=row_index,
            col=col_index,
            column_header=(row_index, col_index) in html_parser.header_positions,
        )
        for row_index, row in enumerate(rows)
        for col_index, text in enumerate(row)
        if text
    ]
    markdown = "\n".join(" | ".join(row) for row in rows if any(row))
    return TableBlock(
        page_no=page_no,
        rows=rows,
        cells=cells,
        bbox=_bbox(block.get("bbox")),
        markdown=markdown,
        html=table_html,
        title=_table_title(block),
    )


def structured_content_to_pages(
    structured: dict[str, Any],
    *,
    source_file: str,
    file_hash: str,
) -> list[PageBlock]:
    raw_pages = structured.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise RuntimeError("MinerU returned no structured pages")

    pages: list[PageBlock] = []
    for fallback_index, raw_page in enumerate(raw_pages):
        if not isinstance(raw_page, dict):
            continue
        try:
            page_no = int(raw_page.get("page_idx", fallback_index)) + 1
        except (TypeError, ValueError):
            page_no = fallback_index + 1
        text_lines: list[str] = []
        tables: list[TableBlock] = []
        raw_blocks = raw_page.get("blocks", [])
        if not isinstance(raw_blocks, list):
            raw_blocks = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                continue
            block_type = str(raw_block.get("type", "")).strip().lower()
            if block_type == "table":
                table = _table_block(raw_block, page_no=page_no)
                if not table.html or not table.rows:
                    raise RuntimeError(
                        f"MinerU table is missing usable HTML on page {page_no}"
                    )
                tables.append(table)
                continue
            if block_type in _SKIPPED_TEXT_TYPES:
                continue
            if text := _block_text(raw_block):
                text_lines.append(text)
        pages.append(
            PageBlock(
                page_no=page_no,
                text="\n".join(text_lines),
                tables=tables,
                source_file=source_file,
                content_hash=file_hash,
            )
        )

    if not pages:
        raise RuntimeError("MinerU returned no usable pages")
    return sorted(pages, key=lambda page: page.page_no)


def parse_pdf_with_mineru(
    pdf_path: Path,
    *,
    file_hash: str,
    tier: str = "standard",
    ocr_mode: str = "auto",
) -> list[PageBlock]:
    """调用 MinerU 4.x Python API，一次性解析全部页。"""
    mineru_parse = _load_mineru_parse()
    logger.info(
        "parse_pdf start backend=mineru file=%s tier=%s ocr_mode=%s",
        pdf_path.name,
        tier,
        ocr_mode,
    )
    result = mineru_parse(
        pdf_path,
        tier=tier,
        ocr_mode=ocr_mode,
        page_range="all",
    )
    structured = result.structured_content()
    if not isinstance(structured, dict):
        raise RuntimeError("MinerU structured_content() did not return a dict")
    pages = structured_content_to_pages(
        structured,
        source_file=pdf_path.name,
        file_hash=file_hash,
    )
    table_count = sum(len(page.tables) for page in pages)
    logger.info(
        "parse_pdf ok backend=mineru file=%s pages=%d tables=%d hash=%s",
        pdf_path.name,
        len(pages),
        table_count,
        file_hash[:16],
    )
    return pages
