from app.eval.dify_compare import (
    dify_configured,
    has_page_cite,
    looks_refuse,
    render_markdown,
    score_item,
    summarize,
)


def test_page_cite_from_text_or_structured_citation():
    assert has_page_cite("风险在第三节，见第 87 页。")
    assert has_page_cite("据年报[1]所述")
    assert has_page_cite("正文无页码", [{"doc_id": "002594_2024", "page": 12, "kind": "rag"}])
    assert not has_page_cite("营收 7771 亿元", [{"doc_id": "facts", "page": 0, "kind": "facts"}])


def test_refuse_phrases():
    assert looks_refuse("文档中未找到相关信息")
    assert looks_refuse("")
    assert not looks_refuse("比亚迪 2024 年风险因素包括汇率与原材料。")


def test_score_and_summary_without_http():
    item = {
        "id": "dify-003",
        "category": "rag",
        "question": "风险因素",
        "expect": {"must_page_cite": True, "must_refuse": False},
    }
    dify = {"text": "见年报描述", "latency_ms": 800, "has_page_cite": False, "refuse": False}
    regops = {
        "text": "汇率风险[1]",
        "latency_ms": 1200,
        "has_page_cite": True,
        "refuse": False,
        "route": "rag",
    }
    row = score_item(item, dify, regops)
    assert row["dify_page_ok"] is False
    assert row["regops_page_ok"] is True
    summary = summarize([row])
    assert summary["n"] == 1
    assert summary["page_cite_rate_dify"] == 0.0
    assert summary["page_cite_rate_regops"] == 1.0
    assert summary["skipped"] is None


def test_skip_markdown_when_dify_down():
    report = {"summary": summarize([], skipped="未配置 DIFY_APP_KEY"), "results": []}
    text = render_markdown(report)
    assert "跳过" in text
    assert "准确率" not in text or "不是准确率" in text


def test_dify_configured_requires_key(monkeypatch):
    monkeypatch.delenv("DIFY_APP_KEY", raising=False)
    assert dify_configured(base_url="http://localhost:1380/v1", api_key="") is False
    assert dify_configured(base_url="http://localhost:1380/v1", api_key="app-x") is True
