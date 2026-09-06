"""W1 聊天黄金集形状 + 闭卷判分（不调 LLM）。"""

import pytest

from app.eval.registry import GOLDEN_DIR
from app.eval.w1_chat_runner import (
    grade_contains,
    is_refusal,
    load_golden,
    resolve_eval_chat_model,
    run_item,
    summarize,
)

GOLDEN_PATH = GOLDEN_DIR / "w1_chat_30.json"
ALLOWED_CATEGORIES = {
    "clause",
    "accounting",
    "banking",
    "market",
    "macro",
    "securities",
    "credit",
}


def test_golden_set_shape():
    payload = load_golden(GOLDEN_PATH)
    items = payload["items"]
    ids = [item["id"] for item in items]

    assert payload["version"] == "w1-v2"
    assert len(items) == 30
    assert len(set(ids)) == 30
    assert set(ids) == {f"w1-{i:03d}" for i in range(1, 31)}

    for item in items:
        missing = {"id", "category", "question", "expected", "grading", "source_doc", "why_clean"} - set(
            item
        )
        assert not missing, f"{item.get('id')} 缺字段 {missing}"
        assert item["grading"] == "contains"
        assert item["category"] != "number"
        assert item["category"] in ALLOWED_CATEGORIES
        assert item["expected"].strip()
        assert "numeric_tolerance" not in item


def test_grade_contains_half_keywords():
    ok, _ = grade_contains("核心一级资本充足率和总资本充足率", "核心一级资本充足率|一级资本充足率|总资本充足率")
    assert ok
    ok, _ = grade_contains("这是无关回复", "核心一级资本充足率|一级资本充足率|总资本充足率")
    assert not ok


def test_is_refusal_short_apology():
    assert is_refusal("抱歉，我无法确定。")
    assert not is_refusal("拨备覆盖率衡量贷款损失准备对不良贷款的覆盖程度。" * 3)


def test_summarize_refuse_rate_and_by_category():
    results = [
        {"category": "clause", "status": "pass", "latency_ms": 10},
        {"category": "clause", "status": "fail", "latency_ms": 20},
        {"category": "accounting", "status": "refuse", "latency_ms": 30},
    ]
    summary = summarize(results)
    assert summary["total"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["refused"] == 1
    assert summary["accuracy"] == round(1 / 3, 4)
    assert summary["refuse_rate"] == round(1 / 3, 4)
    assert "number_error_rate" not in summary
    assert summary["by_category"]["clause"]["passed"] == 1
    assert summary["by_category"]["clause"]["accuracy"] == 0.5
    assert summary["by_category"]["accounting"]["refused"] == 1


def test_resolve_eval_chat_model_requested_and_default():
    assert (
        resolve_eval_chat_model(
            "Qwen",
            available=["deepseek", "qwen"],
            default_model="deepseek",
        )
        == "qwen"
    )
    assert (
        resolve_eval_chat_model(
            "",
            available=["deepseek", "qwen"],
            default_model="deepseek",
        )
        == "deepseek"
    )
    assert (
        resolve_eval_chat_model(
            None,
            available=["qwen"],
            default_model="deepseek",
        )
        == "qwen"
    )


def test_resolve_eval_chat_model_rejects_unknown():
    with pytest.raises(ValueError, match="unsupported model: gpt"):
        resolve_eval_chat_model("gpt", available=["deepseek"], default_model="deepseek")


def test_run_item_sends_model_to_chat():
    captured: dict = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "reply": "核心一级资本充足率、一级资本充足率、总资本充足率",
                "model": captured.get("model"),
            }

    class _Client:
        def post(self, url: str, json: dict):
            captured.update(json)
            captured["url"] = url
            return _Response()

    item = {
        "id": "w1-001",
        "category": "clause",
        "question": "资本充足率三个层次？",
        "expected": "核心一级资本充足率|一级资本充足率|总资本充足率",
        "grading": "contains",
    }
    row = run_item(_Client(), "http://example.test", item, 0.0, model="qwen")
    assert captured["url"].endswith("/chat")
    assert captured["use_rag"] is False
    assert captured["model"] == "qwen"
    assert row["model"] == "qwen"
    assert row["passed"] is True

