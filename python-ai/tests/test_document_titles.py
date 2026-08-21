from app.documents.titles import format_company_report_title, resolve_document_titles


def test_format_company_report_title():
    assert format_company_report_title(company_code="002594", report_year=2024) == "比亚迪2024年年度报告"
    assert format_company_report_title(company_code="000333", report_year=2024) == "美的集团2024年年度报告"


class _FakeCursor:
    def __init__(self, pdf_rows, session_rows):
        self.pdf_rows = pdf_rows
        self.session_rows = session_rows
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, _sql, params):
        self.calls += 1
        if self.calls == 1:
            self._rows = self.pdf_rows
        else:
            self._rows = self.session_rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, pdf_rows, session_rows):
        self.pdf_rows = pdf_rows
        self.session_rows = session_rows

    def cursor(self):
        return _FakeCursor(self.pdf_rows, self.session_rows)


def test_resolve_document_titles_from_pdf_metadata():
    conn = _FakeConn(
        [("002594_2024", "002594_2024_annual", "002594_2024_annual.pdf", "002594", 2024, "annual_report")],
        [],
    )
    titles = resolve_document_titles(conn, ["002594_2024"])
    assert titles["002594_2024"] == "比亚迪2024年年度报告"
