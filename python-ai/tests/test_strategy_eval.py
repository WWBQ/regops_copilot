"""W8-2 四策略对照：30 题 fixture，不调 LLM。"""

from app.eval.registry import GOLDEN_DIR, validate_golden_payload
from app.eval.strategy_runner import (
    STRATEGIES,
    load_golden,
    render_markdown,
    run_strategy_eval,
)

GOLDEN_PATH = GOLDEN_DIR / "w8_prompt_30.json"


def test_golden_set_shape_and_discrimination():
    payload = load_golden(GOLDEN_PATH)
    items = payload["items"]
    ids = [item["id"] for item in items]
    assert len(items) == 30
    assert len(set(ids)) == 30
    assert validate_golden_payload(payload, runner="w8_strategy") == 30
    categories = {item["category"] for item in items}
    assert categories == {
        "concept",
        "numeric_unbacked",
        "numeric_trap",
        "refuse",
        "format",
    }
    examples = " ".join(
        str(item.get("good_reply") or "") + str(item.get("question") or "") for item in items[:3]
    )
    assert "法定存款准备金率" not in examples


def test_strategy_eval_comparison_story():
    report = run_strategy_eval(golden_path=GOLDEN_PATH, seed=42)
    summary = report["summary"]
    assert summary["n"] == 30
    assert summary["backend"] == "fixture"
    by_strategy = summary["by_strategy"]
    assert set(by_strategy) == set(STRATEGIES)
    zero = by_strategy["zero_shot"]
    few = by_strategy["few_shot"]
    cot = by_strategy["cot"]
    react = by_strategy["react"]
    assert few["accuracy"] > zero["accuracy"]
    assert react["accuracy"] < zero["accuracy"]
    assert cot["number_error_rate"] > zero["number_error_rate"]
    assert react["number_error_rate"] > zero["number_error_rate"]
    assert react["avg_tokens"] > zero["avg_tokens"]
    assert react["latency_p50_ms"] > zero["latency_p50_ms"]
    concept = summary["by_category_strategy"]["concept"]
    assert concept["few_shot"]["accuracy"] > concept["zero_shot"]["accuracy"]
    notes = " ".join(item["reason"] for item in summary["when_not_worth"])
    assert "ReAct" in notes or "react" in notes.lower() or "开放 ReAct" in notes
    markdown = render_markdown(report)
    assert "Zero-shot" in markdown
    assert "策略取舍" in markdown
    other = run_strategy_eval(golden_path=GOLDEN_PATH, seed=7)
    assert other["summary"]["item_order"] != summary["item_order"]
    assert other["summary"]["by_strategy"]["zero_shot"]["accuracy"] == zero["accuracy"]
