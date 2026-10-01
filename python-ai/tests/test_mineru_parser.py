from pathlib import Path

import pytest

from app.ingest.mineru_parser import parse_pdf_with_mineru, structured_content_to_pages
from app.ingest.parser import ParseError, normalize_parser_backend, parse_pdf


def _structured_result() -> dict:
    return {
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {"type": "title", "content": "第三节 管理层讨论与分析"},
                    {"type": "text", "content": "公司持续推进海外渠道建设。"},
                    {
                        "type": "table",
                        "bbox": [10, 20, 300, 400],
                        "content": {
                            "table_caption": [{"content": "主要财务指标"}],
                            "html": (
                                "<table><tr><th>项目</th><th>2024年</th></tr>"
                                "<tr><td>营业收入</td><td>100亿元</td></tr></table>"
                            ),
                        },
                    },
                    {"type": "page_footer", "content": "1 / 200"},
                ],
            }
        ]
    }


def test_structured_content_to_pages_preserves_table_html():
    pages = structured_content_to_pages(
        _structured_result(),
        source_file="report.pdf",
        file_hash="sha256:demo",
    )

    assert len(pages) == 1
    assert pages[0].page_no == 1
    assert "海外渠道" in pages[0].text
    assert "1 / 200" not in pages[0].text
    table = pages[0].tables[0]
    assert table.title == "主要财务指标"
    assert table.rows == [["项目", "2024年"], ["营业收入", "100亿元"]]
    assert table.markdown == "项目 | 2024年\n营业收入 | 100亿元"
    assert table.html.startswith("<table>")
    assert table.bbox == (10.0, 20.0, 300.0, 400.0)
    assert table.cells[0].column_header is True


def test_parse_pdf_with_mineru_requests_all_pages(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 demo")
    calls: dict = {}

    class FakeResult:
        def structured_content(self):
            return _structured_result()

    def fake_parse(path, **kwargs):
        calls["path"] = path
        calls.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(
        "app.ingest.mineru_parser._load_mineru_parse",
        lambda: fake_parse,
    )

    pages = parse_pdf_with_mineru(
        pdf,
        file_hash="sha256:demo",
        tier="advanced",
        ocr_mode="ocr",
    )

    assert pages[0].source_file == "report.pdf"
    assert calls == {
        "path": pdf,
        "tier": "advanced",
        "ocr_mode": "ocr",
        "page_range": "all",
    }


def test_parse_pdf_dispatches_to_mineru(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 demo")
    calls: dict = {}

    def fake_mineru(path, **kwargs):
        calls["path"] = path
        calls.update(kwargs)
        return []

    monkeypatch.setattr("app.ingest.mineru_parser.parse_pdf_with_mineru", fake_mineru)

    assert parse_pdf(pdf, backend="mineru") == []
    assert calls["path"] == pdf.resolve()
    assert calls["file_hash"].startswith("sha256:")


def test_unknown_parser_backend_is_rejected():
    with pytest.raises(ParseError, match="unsupported document parser backend"):
        normalize_parser_backend("unknown")


def test_mineru_table_without_html_fails_explicitly():
    structured = {
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {
                        "type": "table",
                        "content": {"table_caption": ["重要财务数据"], "html": ""},
                    }
                ],
            }
        ]
    }

    with pytest.raises(RuntimeError, match="missing usable HTML on page 1"):
        structured_content_to_pages(
            structured,
            source_file="report.pdf",
            file_hash="sha256:demo",
        )
