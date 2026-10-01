import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from app.asknum.slots import parse_slots
from app.db.chunk_repository import ChunkHit
from app.eval.rag_compare_runner import run_rag_compare_eval
from app.eval.registry import GOLDEN_DIR, validate_golden_payload
from app.rag.comparison import plan_comparison_scope, prepare_multi_company_rag


@pytest.fixture(autouse=True)
def _stable_company_aliases(monkeypatch):
    from app.asknum.aliases import BUILTIN_COMPANY_ALIASES

    monkeypatch.setattr(
        "app.asknum.aliases.company_aliases",
        lambda: dict(BUILTIN_COMPANY_ALIASES),
    )
    monkeypatch.setattr(
        "app.rag.comparison.company_aliases",
        lambda: dict(BUILTIN_COMPANY_ALIASES),
    )


def _hit(doc_id: str, content: str, *, page: int = 1) -> ChunkHit:
    return ChunkHit(
        doc_id=doc_id,
        chunk_index=0,
        content=content,
        metadata={"page": page},
        score=0.86,
        vector_score=0.86,
    )


def _patch_citation_dependencies(monkeypatch):
    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.rag.comparison.get_connection", fake_conn)
    monkeypatch.setattr(
        "app.rag.comparison.resolve_document_titles",
        lambda _conn, ids: {doc_id: f"报告 {doc_id}" for doc_id in ids},
    )


def test_plan_comparison_scope_uses_latest_common_year_and_isolates_companies():
    slots = parse_slots("比亚迪和长城汽车的供应链风险有哪些差异")

    plan = plan_comparison_scope(
        slots=slots,
        all_doc_ids=[
            "002594_2024",
            "002594_2023",
            "601633_2024",
            "601633_2023",
            "000333_2024",
        ],
        dept="research",
    )

    assert plan.selected_years == (2024,)
    assert plan.missing == {}
    assert plan.company_doc_ids == {
        "002594": ("002594_2024",),
        "601633": ("601633_2024",),
    }


def test_prepare_multi_company_rag_retrieves_each_company_independently(monkeypatch):
    _patch_citation_dependencies(monkeypatch)
    monkeypatch.setattr(
        "app.rag.comparison.collect_rag_doc_ids",
        lambda _session_id: [
            "002594_2024",
            "002594_2023",
            "601633_2024",
            "601633_2023",
        ],
    )
    calls: list[dict] = []

    def fake_retrieve(**kwargs):
        calls.append(kwargs)
        doc_id = kwargs["doc_ids"][0]
        company = "比亚迪" if doc_id.startswith("002594") else "长城汽车"
        return [_hit(doc_id, f"{company}披露了供应链风险。", page=18)], {
            "final_hit_count": 1
        }

    monkeypatch.setattr(
        "app.rag.comparison.retrieve_relevant_hits_for_docs",
        fake_retrieve,
    )
    document_service = MagicMock()
    document_service.viewer_url.side_effect = (
        lambda doc_id, page: f"http://test/{doc_id}#page={page}"
    )

    result = prepare_multi_company_rag(
        question="比亚迪和长城汽车的供应链风险有哪些差异",
        slots=parse_slots("比亚迪和长城汽车的供应链风险有哪些差异"),
        document_service=document_service,
        dept="research",
    )

    assert result.blocked_reply is None
    assert result.answer is not None
    assert result.selected_years == (2024,)
    assert [call["doc_ids"] for call in calls] == [
        ["002594_2024"],
        ["601633_2024"],
    ]
    assert [call["rerank_candidates"] for call in calls] == [24, 24]
    assert "比亚迪" not in calls[1]["question"]
    assert "长城汽车" not in calls[0]["question"]
    assert len(result.citations) == 2
    prompt = result.answer.messages[-1]["content"]
    assert "【比亚迪（002594）证据】" in prompt
    assert "【长城汽车（601633）证据】" in prompt


def test_prepare_multi_company_rag_blocks_when_one_company_has_no_evidence(monkeypatch):
    _patch_citation_dependencies(monkeypatch)
    monkeypatch.setattr(
        "app.rag.comparison.collect_rag_doc_ids",
        lambda _session_id: ["002594_2024", "601633_2024"],
    )

    def fake_retrieve(**kwargs):
        if kwargs["doc_ids"] == ["002594_2024"]:
            return [_hit("002594_2024", "比亚迪披露供应链风险。")], {}
        return [], {}

    monkeypatch.setattr(
        "app.rag.comparison.retrieve_relevant_hits_for_docs",
        fake_retrieve,
    )

    result = prepare_multi_company_rag(
        question="比亚迪和长城汽车的供应链风险有哪些差异",
        slots=parse_slots("比亚迪和长城汽车的供应链风险有哪些差异"),
        document_service=MagicMock(),
        dept="research",
    )

    assert result.answer is None
    assert result.blocked_reply is not None
    assert "长城汽车：没有达到相关性阈值的直接证据" in result.blocked_reply
    assert "不会让模型补全" in result.blocked_reply
    assert len(result.citations) == 1


def test_prepare_multi_company_rag_blocks_before_retrieval_without_common_year(
    monkeypatch,
):
    retrieve = MagicMock()
    monkeypatch.setattr(
        "app.rag.comparison.collect_rag_doc_ids",
        lambda _session_id: ["002594_2024", "601633_2023"],
    )
    monkeypatch.setattr(
        "app.rag.comparison.retrieve_relevant_hits_for_docs",
        retrieve,
    )

    result = prepare_multi_company_rag(
        question="比亚迪和长城汽车的供应链风险有哪些差异",
        slots=parse_slots("比亚迪和长城汽车的供应链风险有哪些差异"),
        document_service=MagicMock(),
        dept="research",
    )

    assert result.answer is None
    assert result.selected_years == ()
    assert result.blocked_reply is not None
    assert "共同覆盖的报告年度" in result.blocked_reply
    retrieve.assert_not_called()


def test_prepare_multi_company_rag_applies_department_acl_before_retrieval(monkeypatch):
    retrieve = MagicMock()
    monkeypatch.setattr(
        "app.rag.comparison.collect_rag_doc_ids",
        lambda _session_id: ["002594_2024", "000333_2024"],
    )
    monkeypatch.setattr(
        "app.rag.comparison.retrieve_relevant_hits_for_docs",
        retrieve,
    )

    result = prepare_multi_company_rag(
        question="比亚迪和美的集团的供应链风险有哪些差异",
        slots=parse_slots("比亚迪和美的集团的供应链风险有哪些差异"),
        document_service=MagicMock(),
        dept="research",
    )

    assert result.answer is None
    assert result.blocked_reply is not None
    assert "美的集团" in result.blocked_reply
    assert "当前可访问资料" in result.blocked_reply
    retrieve.assert_not_called()


def test_rag_compare_golden_set_is_perfect():
    path = GOLDEN_DIR / "rag_compare_16.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert validate_golden_payload(payload, runner="rag_compare") == 16
    report = run_rag_compare_eval(golden_path=path)

    assert report["summary"]["total"] == 16
    assert report["summary"]["accuracy"] == 1.0
    assert report["summary"]["company_scope_accuracy"] == 1.0
    assert report["summary"]["period_accuracy"] == 1.0
    assert report["summary"]["false_compare_rate"] == 0.0
