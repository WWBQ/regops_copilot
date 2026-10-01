from __future__ import annotations

from app.ingest.artifact import SCHEMA_VERSION, blocks_from_json_bytes, blocks_to_json_bytes, loads_artifact
from app.ingest.models import PageBlock, TableBlock, TableCellBlock


def _sample_blocks() -> list[PageBlock]:
    cell = TableCellBlock(text="100", row=0, col=1, bbox=(1.0, 2.0, 3.0, 4.0))
    table = TableBlock(
        page_no=1,
        rows=[["a", "100"]],
        cells=[cell],
        markdown="| a | 100 |",
        html="<table><tr><td>a</td><td>100</td></tr></table>",
        title="示例表",
    )
    page = PageBlock(
        page_no=1,
        text="示例正文",
        tables=[table],
        source_file="demo.pdf",
        content_hash="sha256:demo",
    )
    return [page]


def test_artifact_roundtrip_bytes():
    blocks = _sample_blocks()
    restored = blocks_from_json_bytes(blocks_to_json_bytes(blocks))
    assert len(restored) == 1
    assert restored[0].text == "示例正文"
    assert restored[0].tables[0].cells[0].bbox == (1.0, 2.0, 3.0, 4.0)
    assert restored[0].tables[0].html.startswith("<table>")
    assert restored[0].tables[0].title == "示例表"


def test_loads_artifact_metadata():
    blocks = _sample_blocks()
    body = blocks_to_json_bytes(blocks)
    artifact = loads_artifact(body)
    assert artifact.schema_version == SCHEMA_VERSION
    assert artifact.page_count == 1
    assert artifact.table_count == 1
    assert artifact.content_hash == "sha256:demo"
