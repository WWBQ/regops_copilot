from app.rag.company_scope import filter_doc_ids_by_question, filter_doc_ids_for_question
from app.rag.dept_scope import apply_retrieval_scope, filter_doc_ids_for_dept


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


def test_yoy_question_keeps_prior_year_docs():
    scoped = filter_doc_ids_by_question(
        ["002594_2024", "002594_2023", "000333_2024"],
        "比亚迪2024年营收同比多少",
    )
    assert scoped == ["002594_2024", "002594_2023"]


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


def test_unknown_company_returns_empty():
    scoped = filter_doc_ids_by_question(
        ["002594_2024", "000333_2024"],
        "宁德时代2024年净利润是多少",
    )
    assert scoped == []


def test_missing_year_returns_empty_when_company_named():
    scoped = filter_doc_ids_by_question(["002594_2024"], "比亚迪2099年营业收入是多少")
    assert scoped == []


def test_session_docs_kept_when_corpus_empty():
    scoped = filter_doc_ids_by_question(
        ["sess_abc", "002594_2024"],
        "宁德时代2024年净利润是多少",
    )
    assert scoped == ["sess_abc"]


def test_research_dept_drops_midea():
    kept = filter_doc_ids_for_dept(
        ["002594_2024", "000333_2024", "sess_x"],
        "research",
    )
    assert kept == ["002594_2024", "sess_x"]


def test_unauthenticated_dept_does_not_filter():
    docs = ["002594_2024", "000333_2024"]
    assert filter_doc_ids_for_dept(docs, None) == docs
    assert apply_retrieval_scope(docs, "美的集团2024年营业收入是多少", None) == ["000333_2024"]


def test_research_asking_midea_is_empty():
    scoped = apply_retrieval_scope(
        ["002594_2024", "601633_2024", "000333_2024"],
        "美的集团2024年营业收入是多少",
        "research",
    )
    assert scoped == []


def test_compliance_can_read_catl_and_moutai():
    docs = ["002594_2024", "300750_2024", "600519_2024"]
    assert apply_retrieval_scope(docs, "宁德时代2024年净利润是多少", "compliance") == ["300750_2024"]
    assert apply_retrieval_scope(docs, "贵州茅台2024年营业收入是多少", "research") == []
