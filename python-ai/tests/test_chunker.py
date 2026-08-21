from app.ingest.chunker import TextChunk, chunk_page_blocks
from app.ingest.models import PageBlock, TableBlock


def test_chunk_page_blocks_includes_table_markdown():
    blocks = [
        PageBlock(
            page_no=27,
            text="4、研发投入",
            tables=[
                TableBlock(
                    page_no=27,
                    rows=[["项目", "2024年"], ["研发费用", "531.9亿元"]],
                    markdown="项目 | 2024年\n研发费用 | 531.9亿元",
                )
            ],
            source_file="002594_2024_annual.pdf",
            content_hash="sha256:demo",
        )
    ]
    chunks = chunk_page_blocks(
        blocks,
        doc_id="002594_2024",
        source_file="002594_2024_annual.pdf",
        content_hash="sha256:demo",
    )
    assert len(chunks) == 1
    assert "531.9亿元" in chunks[0].content
    assert chunks[0].metadata["has_table"] is True


def test_chunk_page_blocks_splits_long_page():
    text = "风险因素。" * 200
    blocks = [
        PageBlock(
            page_no=10,
            text=text,
            tables=[],
            source_file="demo.pdf",
            content_hash="sha256:demo",
        )
    ]
    chunks = chunk_page_blocks(
        blocks,
        doc_id="000333_2024",
        source_file="demo.pdf",
        content_hash="sha256:demo",
        chunk_size=512,
        chunk_overlap=128,
    )
    assert len(chunks) > 1
    assert chunks[0].metadata["page"] == 10
    assert chunks[0].doc_id == "000333_2024"


def test_chunk_skips_empty_page():
    blocks = [
        PageBlock(page_no=1, text="   ", tables=[], source_file="d.pdf", content_hash="h"),
        PageBlock(page_no=2, text="有效段落内容。" * 5, tables=[], source_file="d.pdf", content_hash="h"),
    ]
    chunks = chunk_page_blocks(
        blocks,
        doc_id="x",
        source_file="d.pdf",
        content_hash="h",
    )
    assert len(chunks) == 1
    assert chunks[0].metadata["page"] == 2
