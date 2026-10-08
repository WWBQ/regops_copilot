"""显式设置 RUN_AGENT_PG_TESTS=1 才访问本机 PostgreSQL。"""
import os
import unittest
from uuid import uuid4

from langgraph.checkpoint.base import empty_checkpoint

from agent.core.persistence import make_postgres_checkpointer, make_postgres_langgraph_store
from agent.core.settings import AGENT_DATABASE_URL
from agent.store.postgres_store import PostgresBusinessStore


@unittest.skipUnless(os.getenv("RUN_AGENT_PG_TESTS") == "1", "requires PostgreSQL")
class PostgresPersistenceTest(unittest.TestCase):
    def test_checkpoint_and_memory_round_trip(self):
        thread_id = f"test_{uuid4().hex}"
        saver, saver_conn = make_postgres_checkpointer(AGENT_DATABASE_URL)
        memory, memory_conn = make_postgres_langgraph_store(AGENT_DATABASE_URL)
        namespace = ("test_migration", thread_id)
        try:
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = {"messages": ["persisted"]}
            checkpoint["channel_versions"] = {"messages": "1"}
            checkpoint["updated_channels"] = ["messages"]
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            saver.put(config, checkpoint, {"source": "input", "step": 0, "parents": {}}, {"messages": "1"})
            self.assertEqual(saver.get_tuple(config).checkpoint["channel_values"]["messages"], ["persisted"])
            memory.put(namespace, "memo", {"text": "persisted"})
            self.assertEqual(memory.get(namespace, "memo").value["text"], "persisted")
        finally:
            saver.delete_thread(thread_id)
            memory.delete(namespace, "memo")
            saver_conn.close()
            memory_conn.close()

    def test_business_store_round_trip(self):
        key = uuid4().hex
        thread_id = f"test_{key}_thread"
        run_id = f"test_{key}_run"
        result_id = f"test_{key}_result"
        store = PostgresBusinessStore(AGENT_DATABASE_URL)
        try:
            store.upsert_thread(thread_id=thread_id, title="测试会话")
            store.record_run(run_id=run_id, thread_id=thread_id, status="running", user_question="初筛测试")
            store.upsert_agent_trace_event(
                event_id=f"{run_id}_tool", run_id=run_id, thread_id=thread_id,
                phase="tool", label="lookup_financial_facts", status="completed",
            )
            saved = store.save_risk_audit_result(
                result_id=result_id, run_id=run_id, thread_id=thread_id,
                payload={
                    "company_code": "000333", "company_name": "测试公司", "year": 2024,
                    "status": "needs_review", "summary": "测试", "evidence_gaps": [],
                    "findings": [{
                        "risk_type": "test", "severity": "medium", "conclusion": "待核查",
                        "evidence_ids": [1], "data_points": [], "uncertainty": "测试",
                        "review_question": "是否需要核查？",
                    }],
                },
                report_markdown="测试报告", answer_hash="test-hash",
            )
            self.assertEqual(len(saved["findings"]), 1)
            self.assertEqual(store.list_run_monitor(owner_prefix=f"test_{key}_")["total"], 1)
            self.assertEqual(store.get_agent_run_trace(run_id=run_id, owner_prefix=f"test_{key}_")["title"], "初筛测试")
            store.close()
            store = PostgresBusinessStore(AGENT_DATABASE_URL)
            self.assertEqual(len(store.list_risk_audit_results(thread_id)), 1)
        finally:
            store.delete_thread(thread_id)
            store.close()
