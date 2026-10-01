from app.ingest.chunker import (
    chunk_page_blocks,
    clause_no_from_heading,
    effective_date_from_text,
    is_section_heading,
)
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
    assert chunks[0].content.startswith("4、研发投入")
    assert chunks[0].metadata["has_table"] is True
    assert chunks[0].metadata["content_type"] == "table"
    assert chunks[0].metadata["table_title"] == "4、研发投入"
    assert chunks[0].metadata["table_text"] == chunks[0].content
    assert chunks[0].metadata["table_html"].startswith("<table>")
    assert chunks[0].metadata["company_code"] == "002594"
    assert chunks[0].metadata["year"] == 2024
    assert "dept_acl" not in chunks[0].metadata
    assert "effective_date" not in chunks[0].metadata


def test_chunk_page_blocks_separates_text_and_table_content():
    blocks = [
        PageBlock(
            page_no=8,
            text="经营情况\n公司持续推进海外渠道建设并提升核心产品竞争力。",
            tables=[
                TableBlock(
                    page_no=8,
                    rows=[["地区", "收入"], ["海外", "100亿元"]],
                    markdown="地区 | 收入\n海外 | 100亿元",
                    html="<table><tr><th>地区</th><th>收入</th></tr><tr><td>海外</td><td>100亿元</td></tr></table>",
                    title="分地区收入",
                )
            ],
            source_file="000333_2024.pdf",
            content_hash="sha256:demo",
        )
    ]
    chunks = chunk_page_blocks(
        blocks,
        doc_id="000333_2024",
        source_file="000333_2024.pdf",
        content_hash="sha256:demo",
        parser_backend="mineru",
    )

    text_chunks = [chunk for chunk in chunks if chunk.metadata["content_type"] == "text"]
    table_chunks = [chunk for chunk in chunks if chunk.metadata["content_type"] == "table"]
    assert len(text_chunks) == 1
    assert len(table_chunks) == 1
    assert "100亿元" not in text_chunks[0].content
    assert table_chunks[0].content == "分地区收入\n地区 | 收入\n海外 | 100亿元"
    assert table_chunks[0].metadata["table_id"] == "000333_2024:p8:t1"
    assert text_chunks[0].metadata["parser_backend"] == "mineru"
    assert table_chunks[0].metadata["parser_backend"] == "mineru"


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


def _page(page_no: int, text: str) -> PageBlock:
    return PageBlock(page_no=page_no, text=text, tables=[], source_file="d.pdf", content_hash="h")


def test_is_section_heading_detects_struct_and_page_end_title():
    assert is_section_heading("第三节 管理层讨论与分析")
    assert is_section_heading("4、研发投入")
    assert is_section_heading("本集团 2024 年新推出的车型 21/393", last_on_page=True)
    assert not is_section_heading("单位：人民币元", last_on_page=True)
    assert not is_section_heading("风险因素。", last_on_page=True)
    assert not is_section_heading("2024年", last_on_page=True)


def test_clause_no_and_effective_date_from_heading():
    assert clause_no_from_heading("第十二条 信息披露") == "第十二条"
    assert clause_no_from_heading("第三节 管理层讨论与分析") == "第三节"
    assert effective_date_from_text("自2024年1月1日起施行", "适用范围如下。") == "2024-01-01"
    assert effective_date_from_text("4、研发投入", "2024年研发费用531.9亿元。") is None


def test_page_end_heading_carries_to_next_page():
    body_p21 = "本集团持续推进出海战略，加大芯片与氢能布局。" * 8
    heading = "本集团 2024 年新推出的车型 21/393"
    p22 = (
        "哈弗品牌推出H6、H9等多款车型并陆续上市，坦克品牌发布坦克300、坦克500，"
        "魏牌高山等车型同步投放市场，覆盖燃油、混动与新能源产品矩阵。"
    )
    chunks = chunk_page_blocks(
        [_page(21, f"{body_p21}\n{heading}"), _page(22, p22)],
        doc_id="601633_2024",
        source_file="d.pdf",
        content_hash="h",
    )
    p21_chunks = [c for c in chunks if c.metadata["page"] == 21]
    p22_chunks = [c for c in chunks if c.metadata["page"] == 22]
    assert p21_chunks
    assert p22_chunks
    assert all("新推出的车型" not in c.content or c.metadata.get("section_title") for c in p21_chunks)
    overseas = [c for c in p21_chunks if "出海战略" in c.content]
    assert overseas
    assert "新推出的车型" not in overseas[0].content
    assert any(c.content.startswith("本集团 2024 年新推出的车型") for c in p21_chunks)
    assert all("本集团 2024 年新推出的车型" in c.content for c in p22_chunks)
    assert all(c.metadata.get("section_title", "").startswith("本集团 2024 年新推出的车型") for c in p22_chunks)
    assert "哈弗品牌" in p22_chunks[0].content


def test_long_section_windows_keep_heading_prefix():
    heading = "第一条 适用范围"
    body = "本制度适用于公司全体员工及附属机构。" * 40
    chunks = chunk_page_blocks(
        [_page(3, f"{heading}\n{body}")],
        doc_id="policy",
        source_file="d.pdf",
        content_hash="h",
        chunk_size=80,
        chunk_overlap=16,
    )
    assert len(chunks) > 1
    assert all(c.content.startswith("第一条 适用范围") for c in chunks)
    assert all(c.metadata.get("clause_no") == "第一条" for c in chunks)
    assert all(c.metadata.get("section_title") == "第一条 适用范围" for c in chunks)
    assert all(c.metadata.get("effective_date") is None for c in chunks)
