"""PDF → PageBlock：在 Docling 和 MinerU 之间选择解析器。"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from docling.document_converter import DocumentConverter
from docling_core.types.doc import DocItemLabel
from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.items.table.table import TableItem
from docling_core.types.doc.items.text import ListItem, SectionHeaderItem, TextItem, TitleItem

from app.config import get_settings
from app.ingest.models import BBox, PageBlock, TableBlock, TableCellBlock

logger = logging.getLogger(__name__)

SUPPORTED_PARSER_BACKENDS = ("docling", "mineru")

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


def normalize_parser_backend(value: str | None) -> str:
    """解析并校验后端名，未传时读取环境配置。"""
    selected = (value or get_settings().document_parser_backend).strip().lower()
    if selected not in SUPPORTED_PARSER_BACKENDS:
        known = ", ".join(SUPPORTED_PARSER_BACKENDS)
        raise ParseError(f"unsupported document parser backend: {selected}; choose {known}")
    return selected


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

    try:
        table_html = item.export_to_html(doc=doc).strip()
    except Exception:  # noqa: BLE001 - 表格文本仍可入库，HTML 失败单独降级
        logger.warning("docling table html export failed page=%d", page_no, exc_info=True)
        table_html = ""
    try:
        title = item.caption_text(doc).strip()
    except Exception:  # noqa: BLE001 - caption 是增强字段，不应中断整份 PDF 解析
        logger.warning("docling table caption export failed page=%d", page_no, exc_info=True)
        title = ""

    table_bbox = _bbox_tuple(item.prov[0].bbox) if item.prov else None
    return TableBlock(
        page_no=page_no,
        rows=rows,
        cells=cells,
        bbox=table_bbox,
        markdown=markdown,
        html=table_html,
        title=title,
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


def _parse_pdf_with_docling(
    pdf_path: Path,
    *,
    file_hash: str,
    converter: DocumentConverter | None,
) -> list[PageBlock]:
    source_file = pdf_path.name
    doc_converter = converter or DocumentConverter()
    logger.info("parse_pdf start backend=docling file=%s", source_file)

    try:
        result = doc_converter.convert(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 — 统一向上抛 ParseError
        logger.exception("parse_pdf docling convert failed file=%s", source_file)
        raise ParseError(f"docling convert failed for {pdf_path.name}: {exc}") from exc

    doc = result.document
    if doc.num_pages() == 0:
        logger.error("parse_pdf zero pages backend=docling file=%s", source_file)
        raise ParseError(f"docling returned zero pages: {pdf_path.name}")

    blocks = _docling_to_pages(doc, source_file, file_hash)
    table_count = sum(len(b.tables) for b in blocks)
    logger.info(
        "parse_pdf ok backend=docling file=%s pages=%d tables=%d hash=%s",
        source_file,
        len(blocks),
        table_count,
        file_hash[:16],
    )
    return blocks


def parse_pdf(
    path: str | Path,
    *,
    backend: str | None = None,
    converter: DocumentConverter | None = None,
) -> list[PageBlock]:
    """用指定解析器转换 PDF，返回统一的 PageBlock 列表。"""
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file():
        logger.error("parse_pdf file not found: %s", pdf_path)
        raise ParseError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        logger.error("parse_pdf not a PDF: %s", pdf_path)
        raise ParseError(f"not a PDF file: {pdf_path}")

    selected_backend = normalize_parser_backend(backend)
    file_hash = content_hash(pdf_path)
    if selected_backend == "docling":
        return _parse_pdf_with_docling(
            pdf_path,
            file_hash=file_hash,
            converter=converter,
        )

    if converter is not None:
        raise ParseError("converter is only supported by the docling backend")

    from app.ingest.mineru_parser import parse_pdf_with_mineru

    settings = get_settings()
    try:
        return parse_pdf_with_mineru(
            pdf_path,
            file_hash=file_hash,
            tier=settings.mineru_tier,
            ocr_mode=settings.mineru_ocr_mode,
        )
    except Exception as exc:  # noqa: BLE001 - 对外保持统一 ParseError
        logger.exception("parse_pdf mineru convert failed file=%s", pdf_path.name)
        raise ParseError(f"mineru convert failed for {pdf_path.name}: {exc}") from exc
