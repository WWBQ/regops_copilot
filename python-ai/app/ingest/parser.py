"""PDF → PageBlock（Docling 主路径）。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from docling.document_converter import DocumentConverter
from docling_core.types.doc import DocItemLabel
from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.items.table.table import TableItem
from docling_core.types.doc.items.text import ListItem, SectionHeaderItem, TextItem, TitleItem

from app.ingest.models import BBox, PageBlock, TableBlock, TableCellBlock

logger = logging.getLogger(__name__)

TEXT_LABELS = frozenset(
    {
        DocItemLabel.TEXT,
        DocItemLabel.TITLE,
        DocItemLabel.SECTION_HEADER,
        DocItemLabel.LIST_ITEM,
        DocItemLabel.PARAGRAPH,
        DocItemLabel.CAPTION,
        DocItemLabel.FOOTNOTE,
    }
)


class ParseError(Exception):
    """解析失败；调用方应写入 ingest_job 错误队列，不静默跳过。"""


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _bbox_tuple(bbox: BoundingBox | None) -> BBox | None:
    if bbox is None:
        return None
    return (bbox.l, bbox.t, bbox.r, bbox.b)


def _primary_page(item) -> int | None:
    prov = getattr(item, "prov", None)
    if prov:
        return prov[0].page_no
    return None


def _item_text(item) -> str | None:
    if isinstance(item, (TextItem, TitleItem, SectionHeaderItem, ListItem)):
        text = (item.text or "").strip()
        return text or None
    text = getattr(item, "text", None)
    if text:
        return str(text).strip()
    return None


def _table_block(item: TableItem, doc, page_no: int) -> TableBlock:
    grid = item.data.grid
    rows = [[cell.text.strip() for cell in row] for row in grid]
    cells: list[TableCellBlock] = []
    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row):
            if not cell.text.strip():
                continue
            cells.append(
                TableCellBlock(
                    text=cell.text.strip(),
                    row=row_idx,
                    col=col_idx,
                    bbox=_bbox_tuple(cell.bbox),
                    column_header=cell.column_header,
                    row_header=cell.row_header,
                )
            )

    markdown_lines: list[str] = []
    for row in rows:
        if any(cell for cell in row):
            markdown_lines.append(" | ".join(row))
    markdown = "\n".join(markdown_lines)

    table_bbox = _bbox_tuple(item.prov[0].bbox) if item.prov else None
    return TableBlock(
        page_no=page_no,
        rows=rows,
        cells=cells,
        bbox=table_bbox,
        markdown=markdown,
    )


def _docling_to_pages(doc, source_file: str, file_hash: str) -> list[PageBlock]:
    num_pages = doc.num_pages()
    text_lines: dict[int, list[str]] = {p: [] for p in range(1, num_pages + 1)}
    tables: dict[int, list[TableBlock]] = {p: [] for p in range(1, num_pages + 1)}

    for item, _level in doc.iterate_items():
        page_no = _primary_page(item)
        if page_no is None or page_no not in text_lines:
            continue

        if isinstance(item, TableItem):
            tables[page_no].append(_table_block(item, doc, page_no))
            continue

        label = getattr(item, "label", None)
        if label in TEXT_LABELS or isinstance(item, (TextItem, TitleItem, SectionHeaderItem, ListItem)):
            text = _item_text(item)
            if text:
                text_lines[page_no].append(text)

    blocks: list[PageBlock] = []
    for page_no in range(1, num_pages + 1):
        blocks.append(
            PageBlock(
                page_no=page_no,
                text="\n".join(text_lines[page_no]),
                tables=tables[page_no],
                source_file=source_file,
                content_hash=file_hash,
            )
        )
    return blocks


def parse_pdf(path: str | Path, *, converter: DocumentConverter | None = None) -> list[PageBlock]:
    """解析 PDF，返回按页排序的 PageBlock 列表。"""
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file():
        logger.error("parse_pdf file not found: %s", pdf_path)
        raise ParseError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        logger.error("parse_pdf not a PDF: %s", pdf_path)
        raise ParseError(f"not a PDF file: {pdf_path}")

    file_hash = content_hash(pdf_path)
    source_file = pdf_path.name
    doc_converter = converter or DocumentConverter()
    logger.info("parse_pdf start file=%s", source_file)

    try:
        result = doc_converter.convert(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 — 统一向上抛 ParseError
        logger.exception("parse_pdf docling convert failed file=%s", source_file)
        raise ParseError(f"docling convert failed for {pdf_path.name}: {exc}") from exc

    doc = result.document
    if doc.num_pages() == 0:
        logger.error("parse_pdf zero pages file=%s", source_file)
        raise ParseError(f"docling returned zero pages: {pdf_path.name}")

    blocks = _docling_to_pages(doc, source_file, file_hash)
    table_count = sum(len(b.tables) for b in blocks)
    logger.info(
        "parse_pdf ok file=%s pages=%d tables=%d hash=%s",
        source_file,
        len(blocks),
        table_count,
        file_hash[:16],
    )
    return blocks
