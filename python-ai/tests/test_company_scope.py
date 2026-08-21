from app.rag.company_scope import filter_doc_ids_for_question


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.last_params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, _sql, params):
        self.last_params = params

    def fetchall(self):
        return self.rows


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _FakeCursor(self.rows)


def test_filter_doc_ids_for_question_scopes_by_company_and_year():
    conn = _FakeConn(
        [
            ("002594_2024", "002594", 2024),
            ("002594_2023", "002594", 2023),
            ("000333_2024", "000333", 2024),
        ]
    )
    scoped = filter_doc_ids_for_question(
        conn,
        ["002594_2024", "002594_2023", "000333_2024"],
        "比亚迪2024年研发投入是多少",
    )
    assert scoped == ["002594_2024"]


def test_filter_doc_ids_scopes_great_wall():
    conn = _FakeConn(
        [
            ("601633_2024", "601633", 2024),
            ("002594_2024", "002594", 2024),
        ]
    )
    scoped = filter_doc_ids_for_question(
        conn,
        ["601633_2024", "002594_2024"],
        "2024 年长城新推出的车型",
    )
    assert scoped == ["601633_2024"]


def test_filter_doc_ids_for_question_keeps_all_when_unscoped():
    conn = _FakeConn([("002594_2024", "002594", 2024)])
    scoped = filter_doc_ids_for_question(conn, ["002594_2024"], "研发投入趋势如何")
    assert scoped == ["002594_2024"]
