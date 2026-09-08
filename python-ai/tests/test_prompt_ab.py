"""W8-3 A/B：n=30 提升约 3% 通常不可信。"""

from app.eval.ab_runner import render_markdown, run_ab_eval
from app.eval.registry import GOLDEN_DIR, validate_golden_payload
from app.eval.stats import assess_ab, mcnemar_exact_p, wilson_interval
from app.eval.strategy_runner import load_golden

GOLDEN_PATH = GOLDEN_DIR / "w8_prompt_30.json"


def test_stats_n30_three_points_not_credible():
    stats = assess_ab(n=30, k_a=21, k_b=22, n01=1, n10=0)
    assert stats["delta"] == 0.0333
    assert stats["crosses_zero"] is True
    assert stats["credible"] is False
    assert "不可信" in stats["verdict"]
    low, high = wilson_interval(22, 30)
    assert low < 22 / 30 < high
    assert mcnemar_exact_p(1, 0) == 1.0


def test_ab_eval_fixture_is_honest():
    payload = load_golden(GOLDEN_PATH)
    assert validate_golden_payload(payload, runner="w8_ab") == 30
    report = run_ab_eval(golden_path=GOLDEN_PATH, seed=42)
    summary = report["summary"]
    assert summary["n"] == 30
    assert summary["k_a"] == 21
    assert summary["k_b"] == 22
    assert summary["n01"] == 1
    assert summary["n10"] == 0
    assert summary["delta"] == 0.0333
    assert summary["credible"] is False
    assert "n=30" in summary["verdict"]
    discordant = [row["id"] for row in report["results"] if row["discordant"]]
    assert discordant == ["w8-011"]
    other = run_ab_eval(golden_path=GOLDEN_PATH, seed=7)
    assert other["summary"]["item_order"] != summary["item_order"]
    assert other["summary"]["k_b"] == 22
    markdown = render_markdown(report)
    assert "credible=false" in markdown
    assert "McNemar" in markdown
