"""PageBlock 序列化 ↔ 解析 JSON 回溯 artifact。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from app.ingest.models import BBox, PageBlock, TableBlock, TableCellBlock

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ParseArtifact:
    schema_version: int
    source_file: str
    content_hash: str
    page_count: int
    table_count: int
    pages: list[PageBlock]

    @property
    def object_suffix(self) -> str:
        return ".parse.json"


def _bbox_to_json(bbox: BBox | None) -> list[float] | None:
    if bbox is None:
        return None
    return [bbox[0], bbox[1], bbox[2], bbox[3]]


def _bbox_from_json(raw: list[float] | None) -> BBox | None:
    if raw is None:
        return None
    return (raw[0], raw[1], raw[2], raw[3])


def page_block_to_dict(page: PageBlock) -> dict[str, Any]:
    return {
        "page_no": page.page_no,
        "text": page.text,
        "source_file": page.source_file,
        "content_hash": page.content_hash,
        "tables": [table_block_to_dict(table) for table in page.tables],
    }


def table_block_to_dict(table: TableBlock) -> dict[str, Any]:
    return {
        "page_no": table.page_no,
        "rows": table.rows,
        "cells": [table_cell_to_dict(cell) for cell in table.cells],
        "bbox": _bbox_to_json(table.bbox),
        "markdown": table.markdown,
        "html": table.html,
        "title": table.title,
    }


def table_cell_to_dict(cell: TableCellBlock) -> dict[str, Any]:
    return {
        "text": cell.text,
        "row": cell.row,
        "col": cell.col,
        "bbox": _bbox_to_json(cell.bbox),
        "column_header": cell.column_header,
        "row_header": cell.row_header,
    }


def page_block_from_dict(raw: dict[str, Any]) -> PageBlock:
    tables = [table_block_from_dict(item) for item in raw.get("tables", [])]
    return PageBlock(
        page_no=int(raw["page_no"]),
        text=str(raw.get("text", "")),
        tables=tables,
        source_file=str(raw.get("source_file", "")),
        content_hash=str(raw.get("content_hash", "")),
    )


def table_block_from_dict(raw: dict[str, Any]) -> TableBlock:
    cells = [table_cell_from_dict(item) for item in raw.get("cells", [])]
    return TableBlock(
        page_no=int(raw["page_no"]),
        rows=raw.get("rows", []),
        cells=cells,
        bbox=_bbox_from_json(raw.get("bbox")),
        markdown=str(raw.get("markdown", "")),
        html=str(raw.get("html", "")),
        title=str(raw.get("title", "")),
    )


def table_cell_from_dict(raw: dict[str, Any]) -> TableCellBlock:
    return TableCellBlock(
        text=str(raw.get("text", "")),
        row=int(raw["row"]),
        col=int(raw["col"]),
        bbox=_bbox_from_json(raw.get("bbox")),
        column_header=bool(raw.get("column_header", False)),
        row_header=bool(raw.get("row_header", False)),
    )


def blocks_to_artifact(blocks: list[PageBlock]) -> ParseArtifact:
    if not blocks:
        raise ValueError("empty parse result")
    table_count = sum(len(page.tables) for page in blocks)
    head = blocks[0]
    return ParseArtifact(
        schema_version=SCHEMA_VERSION,
        source_file=head.source_file,
        content_hash=head.content_hash,
        page_count=len(blocks),
        table_count=table_count,
        pages=blocks,
    )


def artifact_to_dict(artifact: ParseArtifact) -> dict[str, Any]:
    return {
        "schema_version": artifact.schema_version,
        "source_file": artifact.source_file,
        "content_hash": artifact.content_hash,
        "page_count": artifact.page_count,
        "table_count": artifact.table_count,
        "pages": [page_block_to_dict(page) for page in artifact.pages],
    }


def artifact_from_dict(raw: dict[str, Any]) -> ParseArtifact:
    pages = [page_block_from_dict(item) for item in raw.get("pages", [])]
    return ParseArtifact(
        schema_version=int(raw.get("schema_version", 1)),
        source_file=str(raw.get("source_file", "")),
        content_hash=str(raw.get("content_hash", "")),
        page_count=int(raw.get("page_count", len(pages))),
        table_count=int(raw.get("table_count", 0)),
        pages=pages,
    )


def dumps_artifact(artifact: ParseArtifact) -> bytes:
    payload = artifact_to_dict(artifact)
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def loads_artifact(body: bytes) -> ParseArtifact:
    raw = json.loads(body.decode("utf-8"))
    return artifact_from_dict(raw)


def blocks_to_json_bytes(blocks: list[PageBlock]) -> bytes:
    return dumps_artifact(blocks_to_artifact(blocks))


def blocks_from_json_bytes(body: bytes) -> list[PageBlock]:
    return loads_artifact(body).pages
