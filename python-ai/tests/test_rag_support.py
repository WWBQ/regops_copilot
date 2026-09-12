from app.eval.rag_support_runner import summarize, support_coverage


def test_support_coverage_finds_required_phrases():
    found, missing = support_coverage("元UP 与 秦L DM-i 同期上市", ["元UP", "秦L", "海狮07EV"])
    assert found == ["元UP", "秦L"]
    assert missing == ["海狮07EV"]


def test_support_summary_separates_hit_rate_from_coverage():
    results = [
        {"category": "product_enum", "passed": True, "support_coverage": 1.0},
        {"category": "product_enum", "passed": False, "support_coverage": 0.5},
        {"category": "numeric_financial", "passed": True, "support_coverage": 1.0},
    ]
    summary = summarize(results)
    assert summary["count"] == 3
    assert summary["support_hit_rate"] == 0.6667
    assert summary["support_coverage"] == 0.8333
    assert summary["by_category"]["product_enum"]["support_hit_rate"] == 0.5
