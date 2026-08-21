from pathlib import Path

import pytest

from app.config import ROOT_DIR
from app.ingest.parser import ParseError, content_hash, parse_pdf

RAW = ROOT_DIR / "data" / "raw"


def test_content_hash_prefix(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    h = content_hash(pdf)
    assert h.startswith("sha256:")
    assert len(h) == 7 + 64


def test_parse_pdf_missing_raises():
    with pytest.raises(ParseError, match="PDF not found"):
        parse_pdf("/nonexistent/report.pdf")


def test_parse_pdf_not_pdf_suffix(tmp_path: Path):
    txt = tmp_path / "report.txt"
    txt.write_text("not pdf")
    with pytest.raises(ParseError, match="not a PDF"):
        parse_pdf(txt)


@pytest.mark.skipif(not any(RAW.glob("*.pdf")), reason="no PDF fixtures in data/raw")
def test_parse_pdf_returns_page_blocks():
    pdf = next(RAW.glob("*.pdf"))
    blocks = parse_pdf(pdf)
    assert blocks
    assert blocks[0].page_no == 1
    assert blocks[0].source_file == pdf.name
    assert blocks[0].content_hash.startswith("sha256:")
    assert isinstance(blocks[0].text, str)
    assert isinstance(blocks[0].tables, list)
