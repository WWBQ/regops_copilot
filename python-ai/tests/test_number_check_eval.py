"""W6-3 数字校验黄金集：结构 + 误放行门禁。"""

from app.eval.number_check_runner import (
    load_golden,
    render_markdown,
    run_number_check_eval,
)
from app.eval.registry import GOLDEN_DIR, validate_golden_payload

GOLDEN_PATH = GOLDEN_DIR / "w6_number_check_20.json"


def test_golden_set_shape():
    payload = load_golden(GOLDEN_PATH)
    items = payload["items"]
    ids = [item["id"] for item in items]
    assert len(items) == 20
    assert len(set(ids)) == 20
    assert validate_golden_payload(payload, runner="w6_number_check") == 20
    categories = {item["category"] for item in items}
    assert "grounded" in categories
    assert "unbacked" in categories
    assert "unit_error" in categories
    assert "computed" in categories
    for item in items:
        assert isinstance(item["expected_ok"], bool)
        if not item["expected_ok"]:
            assert item.get("expected_categories"), f"{item['id']} 拦截题须声明类别"


def test_number_check_has_no_false_accept():
    report = run_number_check_eval(golden_path=GOLDEN_PATH)
    summary = report["summary"]
    assert summary["total"] == 20
    assert summary["false_accept"] == 0
    assert summary["accuracy"] == 1.0
    assert summary["unit_error_count"] >= 2
    blocked_ids = [row["id"] for row in report["results"] if not row["actual_ok"]]
    assert "nc-011" in blocked_ids
    assert "nc-014" in blocked_ids
    assert "nc-018" in blocked_ids
    markdown = render_markdown(report)
    assert "误放行" in markdown
    assert "量纲" in markdown
