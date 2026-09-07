"""W6-6 审查工作流轨迹黄金集。"""

from app.eval.registry import GOLDEN_DIR, validate_golden_payload
from app.eval.workflow_runner import load_golden, render_markdown, run_workflow_eval

GOLDEN_PATH = GOLDEN_DIR / "w6_workflow_20.json"


def test_golden_set_shape():
    payload = load_golden(GOLDEN_PATH)
    items = payload["items"]
    ids = [item["id"] for item in items]
    assert len(items) == 20
    assert len(set(ids)) == 20
    assert validate_golden_payload(payload, runner="w6_workflow") == 20
    categories = {item["category"] for item in items}
    assert "happy" in categories
    assert "budget" in categories
    assert "injection" in categories
    assert "fabricate" in categories
    assert "unauthorized" in categories


def test_workflow_eval_all_pass():
    report = run_workflow_eval(golden_path=GOLDEN_PATH)
    summary = report["summary"]
    assert summary["total"] == 20
    assert summary["accuracy"] == 1.0
    assert summary["confirmation_rate"] == 1.0
    failed = [row["id"] + ":" + row["detail"] for row in report["results"] if not row["passed"]]
    assert failed == []
    markdown = render_markdown(report)
    assert "轨迹" in markdown
    assert "confirmation_rate" in markdown
    assert "失败定位到节点" in markdown
    assert summary["fail_by_node"] == {}
