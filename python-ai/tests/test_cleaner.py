from app.ingest.cleaner import clean_page_blocks, clean_page_text
from app.ingest.models import PageBlock


def test_clean_page_text_strips_annual_header():
    raw = "比亚迪股份有限公司2024年年度报告全文\n本集团研发投入约为542亿元。"
    cleaned, hits = clean_page_text(raw)
    assert hits == 1
    assert "年度报告全文" not in cleaned
    assert "542亿元" in cleaned


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
