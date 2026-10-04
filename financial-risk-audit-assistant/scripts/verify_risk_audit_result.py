from __future__ import annotations

import tempfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.financial.risk_result import answer_hash, parse_risk_audit_output
from agent.store import LocalSqliteStore


REPORT = """## 初筛结论

经营现金流与利润变化需要人工核查。[1][2]

```risk_audit_result
{"company_code":"000333","company_name":"美的集团","year":2024,"status":"partial","findings":[{"risk_type":"盈利质量","severity":"medium","conclusion":"经营现金流与利润变化需要核查","evidence_ids":[1,2],"data_points":["2024 年净利润","2024 年经营现金流"],"uncertainty":"缺少应收账款账龄明细","review_question":"利润增长是否由非经常性项目驱动？"}],"evidence_gaps":["应收账款账龄明细"],"summary":"发现一条待人工复核的盈利质量线索"}
```
"""


def main() -> None:
    markdown, parsed, error = parse_risk_audit_output(
        REPORT,
        available_citation_ids={1, 2},
    )
    assert error is None
    assert parsed is not None
    assert "risk_audit_result" not in markdown
    assert parsed.findings[0].evidence_ids == [1, 2]

    _, invalid, invalid_error = parse_risk_audit_output(
        REPORT.replace('"evidence_ids":[1,2]', '"evidence_ids":[1,99]'),
        available_citation_ids={1, 2},
    )
    assert invalid is None
    assert invalid_error == "unknown_citation_ids: [99]"

    with tempfile.TemporaryDirectory() as temp_dir:
        store = LocalSqliteStore(Path(temp_dir) / "store.sqlite")
        thread_id = "user_thread"
        run_id = "run-1"
        store.upsert_thread(thread_id=thread_id, title="测试", latest_run_status="running")
        store.record_run(run_id=run_id, thread_id=thread_id, status="running")
        saved = store.save_risk_audit_result(
            result_id="result-1",
            run_id=run_id,
            thread_id=thread_id,
            payload=parsed.model_dump(),
            report_markdown=markdown,
            answer_hash=answer_hash(markdown),
        )
        assert saved["company_code"] == "000333"
        assert saved["evidence_gaps"] == ["应收账款账龄明细"]
        assert saved["findings"][0]["review_status"] == "pending_review"
        assert saved["findings"][0]["evidence_ids"] == [1, 2]
        assert len(store.list_risk_audit_results(thread_id)) == 1
        assert store.delete_thread(thread_id)
        assert store.list_risk_audit_results(thread_id) == []
        store.close()

    print("risk audit structured result verification passed")


if __name__ == "__main__":
    main()
