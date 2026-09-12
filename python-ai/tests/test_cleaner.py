from app.ingest.cleaner import clean_page_blocks, clean_page_text
from app.ingest.models import PageBlock, TableBlock


def test_clean_page_text_strips_annual_header():
    raw = "比亚迪股份有限公司2024年年度报告全文\n本集团研发投入约为542亿元。"
    cleaned, hits, _ = clean_page_text(raw)
    assert hits.get("annual_header_lines") == 1
    assert "年度报告全文" not in cleaned
    assert "542亿元" in cleaned


def test_clean_page_text_strips_meta_and_html():
    raw = (
        "证券代码：002594\n"
        "证券简称：比亚迪\n"
        "<p>本集团研发投入约为542亿元。</p>&nbsp;"
    )
    cleaned, hits, _ = clean_page_text(raw)
    assert hits.get("meta_lines") == 2
    assert hits.get("html_residue", 0) >= 1
    assert "证券代码" not in cleaned
    assert "542亿元" in cleaned
    assert "<p>" not in cleaned


def test_clean_page_text_merges_hard_wraps():
    raw = "公司不存在对生产经营状况、财务状况和持续盈利能力有严重不利影响的\n有关风险因素。"
    cleaned, hits, _ = clean_page_text(raw)
    assert hits.get("hard_wraps") == 1
    assert "影响的有关风险因素" in cleaned.replace(" ", "")


def test_clean_page_blocks_applies_to_all_pages():
    blocks = [
        PageBlock(
            page_no=14,
            text="002594 比亚迪股份有限公司2024年年度报告全文\n正文段落。",
            tables=[],
            source_file="demo.pdf",
            content_hash="h",
        )
    ]
    cleaned, stats = clean_page_blocks(blocks)
    assert "年度报告全文" not in cleaned[0].text
    assert stats.hits.get("annual_header_lines") == 1


def test_clean_page_blocks_dedupes_cross_page_table_headers():
    header = ["项目", "本期金额", "上期金额"]
    blocks = [
        PageBlock(
            page_no=10,
            text="项目 本期金额 上期金额\n营业收入 1 2",
            tables=[TableBlock(page_no=10, rows=[header, ["营业收入", "1", "2"]])],
            source_file="demo.pdf",
            content_hash="h",
        ),
        PageBlock(
            page_no=11,
            text="项目 本期金额 上期金额\n净利润 3 4",
            tables=[TableBlock(page_no=11, rows=[header, ["净利润", "3", "4"]])],
            source_file="demo.pdf",
            content_hash="h",
        ),
    ]
    cleaned, stats = clean_page_blocks(blocks)
    assert cleaned[0].tables[0].rows[0] == header
    assert cleaned[1].tables[0].rows[0] == ["净利润", "3", "4"]
    assert stats.hits.get("cross_page_table_headers") == 1
    assert "项目 本期金额" not in cleaned[1].text
    assert "净利润" in cleaned[1].text
