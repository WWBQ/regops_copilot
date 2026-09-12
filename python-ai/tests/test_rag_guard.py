import json
from pathlib import Path

from app.eval.rag_guard_runner import decide_guard, run_rag_guard_eval
from app.eval.registry import GOLDEN_DIR, validate_golden_payload
from app.rag.dept_scope import DEFAULT_CORPUS_DOC_IDS


def test_decide_guard_chitchat_and_off_corpus():
    assert decide_guard("你好")[0] == "no_intent"
    assert decide_guard("今天天气怎么样")[0] == "no_intent"
    outcome, docs = decide_guard("海康威视（002415）2024年净利润是多少")
    assert outcome == "no_docs"
    assert docs == []
    outcome, docs = decide_guard("比亚迪2099年营业收入是多少")
    assert outcome == "no_docs"
    assert docs == []
    outcome, docs = decide_guard("比亚迪2024年营业收入是多少", dept="research")
    assert outcome == "retrieve"
    assert docs == ["002594_2024"]
    outcome, docs = decide_guard("美的集团2024年营业收入是多少", dept="research")
    assert outcome == "no_docs"
    assert docs == []
    outcome, docs = decide_guard("宁德时代2024年净利润是多少", dept="compliance")
    assert outcome == "retrieve"
    assert docs == ["300750_2024"]


def test_rag_acl_golden_is_perfect():
    payload = json.loads((GOLDEN_DIR / "rag_acl_20.json").read_text(encoding="utf-8"))
    assert validate_golden_payload(payload, runner="rag_acl") == 20
    report = run_rag_guard_eval(golden_path=GOLDEN_DIR / "rag_acl_20.json", task_id="rag_acl")
    summary = report["summary"]
    assert summary["total"] == 20
    assert summary["accuracy"] == 1.0
    assert summary["false_accept_rate"] == 0.0
    assert summary["leak_rate"] == 0.0
    assert set(summary["by_category"]) >= {"allow", "deny", "open_chat"}


def test_rag_refuse_golden_is_perfect():
    payload = json.loads((GOLDEN_DIR / "rag_refuse_20.json").read_text(encoding="utf-8"))
    assert validate_golden_payload(payload, runner="rag_refuse") == 20
    report = run_rag_guard_eval(golden_path=GOLDEN_DIR / "rag_refuse_20.json", task_id="rag_refuse")
    summary = report["summary"]
    assert summary["total"] == 20
    assert summary["accuracy"] == 1.0
    assert summary["false_accept_rate"] == 0.0
    assert all(row["actual_outcome"] != "retrieve" for row in report["results"])


def test_guard_eval_uses_golden_corpus(tmp_path: Path):
    golden = {
        "version": "t",
        "default_params": {"corpus_doc_ids": list(DEFAULT_CORPUS_DOC_IDS)},
        "items": [
            {
                "id": "t-1",
                "category": "deny",
                "question": "美的集团2024年营业收入是多少",
                "dept": "research",
                "expected_outcome": "no_docs",
                "expected_companies": [],
                "forbidden_companies": ["000333"],
            }
        ],
    }
    path = tmp_path / "g.json"
    path.write_text(json.dumps(golden), encoding="utf-8")
    report = run_rag_guard_eval(golden_path=path, task_id="rag_acl")
    assert report["results"][0]["passed"] is True
