"""Ingest 中间结构：PageBlock / TableBlock。"""

from __future__ import annotations

from dataclasses import dataclass, field


BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class TableCellBlock:
    """表格单元格，保留 G3 证据坐标。"""

    text: str
    row: int
    col: int
    bbox: BBox | None = None
    column_header: bool = False
    row_header: bool = False


@dataclass
class TableBlock:
    """单页内一张表（跨页表以首个 prov.page_no 归属）。"""

    page_no: int
    rows: list[list[str]]
    cells: list[TableCellBlock] = field(default_factory=list)
    bbox: BBox | None = None
    markdown: str = ""


@dataclass
class PageBlock:
    """PDF 单页解析结果。"""

    page_no: int
    text: str
    tables: list[TableBlock]
    source_file: str
    content_hash: str
