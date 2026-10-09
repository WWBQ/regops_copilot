import tempfile
import unittest
from pathlib import Path

from agent.store.sqlite_store import LocalSqliteStore


class AgentMonitorStoreTest(unittest.TestCase):
    def test_coding_threads_are_excluded_from_risk_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalSqliteStore(Path(directory) / "store.sqlite")
            try:
                store.upsert_thread(thread_id="user-a_risk-1", title="风险初筛")
                store.upsert_thread(thread_id="user-a_coding_code-1", title="代码任务")
                store.record_run(run_id="risk-run", thread_id="user-a_risk-1", status="completed")
                store.record_run(run_id="code-run", thread_id="user-a_coding_code-1", status="completed")
                risk = store.list_threads(owner_prefix="user-a_", exclude_prefix="user-a_coding_")
                coding = store.list_threads(owner_prefix="user-a_coding_")
                self.assertEqual([item["title"] for item in risk], ["风险初筛"])
                self.assertEqual([item["title"] for item in coding], ["代码任务"])
                monitor = store.list_run_monitor(owner_prefix="user-a_", exclude_prefix="user-a_coding_")
                self.assertEqual(monitor["total"], 1)
                self.assertEqual(monitor["items"][0]["run_id"], "risk-run")
                self.assertEqual(len(monitor["sessions"]), 1)
            finally:
                store.close()

    def test_run_questions_and_session_filter_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalSqliteStore(Path(directory) / "store.sqlite")
            try:
                store.upsert_thread(thread_id="user-a_thread-1", title="会话一")
                store.upsert_thread(thread_id="user-a_thread-2", title="会话二")
                store.upsert_thread(thread_id="user-b_thread-3", title="其他用户会话")
                store.record_run(run_id="run-1", thread_id="user-a_thread-1", status="running", user_question="第一问")
                store.record_run(run_id="run-1", thread_id="user-a_thread-1", status="completed", finished=True)
                store.record_run(run_id="run-2", thread_id="user-a_thread-1", status="running", user_question="第二问")
                store.record_run(run_id="run-3", thread_id="user-a_thread-2", status="running")
                store.upsert_agent_trace_event(
                    event_id="run-3:user", run_id="run-3", thread_id="user-a_thread-2",
                    phase="user", label="轨迹里的问题", status="completed",
                )
                store.record_run(run_id="run-4", thread_id="user-a_thread-2", status="running")
                store.record_run(run_id="run-b", thread_id="user-b_thread-3", status="running", user_question="私有问题")

                all_runs = store.list_run_monitor(owner_prefix="user-a_")
                self.assertEqual(all_runs["total"], 4)
                self.assertEqual(len(all_runs["sessions"]), 2)
                self.assertEqual({item["thread_id"] for item in all_runs["sessions"]},
                                 {"user-a_thread-1", "user-a_thread-2"})
                one_session = store.list_run_monitor(owner_prefix="user-a_", thread_id="user-a_thread-1")
                self.assertEqual(one_session["total"], 2)
                self.assertEqual({item["title"] for item in one_session["items"]}, {"第一问", "第二问"})
                self.assertTrue(all(item["session_title"] == "会话一" for item in one_session["items"]))
                self.assertEqual(store.get_agent_run_trace(run_id="run-1", owner_prefix="user-a_")["title"], "第一问")
                legacy = store.list_run_monitor(owner_prefix="user-a_", thread_id="user-a_thread-2")
                self.assertEqual({item["title"] for item in legacy["items"]},
                                 {"轨迹里的问题", "历史运行（未记录问题）"})
                self.assertEqual(store.list_run_monitor(owner_prefix="user-a_", thread_id="user-b_thread-3")["total"], 0)
            finally:
                store.close()

    def test_trace_is_persistent_scoped_and_contains_no_raw_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.sqlite"
            owner_a = "user-a_"
            store = LocalSqliteStore(path)
            try:
                store.upsert_thread(thread_id="user-a_thread-1", title="初筛")
                store.upsert_thread(thread_id="user-b_thread-2", title="其他用户")
                store.record_run(run_id="run-a", thread_id="user-a_thread-1", status="running")
                store.record_run(run_id="run-b", thread_id="user-b_thread-2", status="running")
                store.upsert_agent_trace_event(
                    event_id="run-a:tool:1", run_id="run-a", thread_id="user-a_thread-1",
                    phase="tool", label="lookup_financial_facts", status="running",
                )
                store.upsert_agent_trace_event(
                    event_id="run-a:tool:1", run_id="run-a", thread_id="user-a_thread-1",
                    phase="tool", label="ignored", status="completed",
                )
                store.upsert_agent_trace_event(
                    event_id="run-b:user", run_id="run-b", thread_id="user-b_thread-2",
                    phase="user", label="private", status="completed",
                )
                trace = store.get_agent_run_trace(run_id="run-a", owner_prefix=owner_a)
                self.assertIsNotNone(trace)
                self.assertEqual(len(trace["events"]), 1)
                self.assertEqual(trace["events"][0]["label"], "lookup_financial_facts")
                self.assertEqual(trace["events"][0]["status"], "completed")
                self.assertIsNotNone(trace["events"][0]["finished_at"])
                self.assertIsNone(store.get_agent_run_trace(run_id="run-b", owner_prefix=owner_a))
                self.assertIsNone(store.get_agent_run_trace(run_id="missing", owner_prefix=owner_a))
            finally:
                store.close()

            reopened = LocalSqliteStore(path)
            try:
                self.assertEqual(len(reopened.get_agent_run_trace(run_id="run-a", owner_prefix=owner_a)["events"]), 1)
                reopened.delete_thread("user-a_thread-1")
                self.assertIsNone(reopened.get_agent_run_trace(run_id="run-a", owner_prefix=owner_a))
                self.assertEqual(reopened._conn.execute("SELECT COUNT(*) FROM agent_trace_events WHERE run_id = 'run-a'").fetchone()[0], 0)
            finally:
                reopened.close()

    def test_runs_are_persistent_and_scoped_to_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.sqlite"
            store = LocalSqliteStore(path)
            try:
                store.upsert_thread(thread_id="user-a_thread-1", title="风险初筛")
                store.upsert_thread(thread_id="user-b_thread-2", title="其他用户")
                store.record_run(run_id="run-a-1", thread_id="user-a_thread-1", status="running")
                store.record_run(run_id="run-a-1", thread_id="user-a_thread-1", status="completed", finished=True)
                store.record_run(run_id="run-a-2", thread_id="user-a_thread-1", status="failed", error="模型超时", finished=True)
                store.record_run(run_id="run-b-1", thread_id="user-b_thread-2", status="running")

                result = store.list_run_monitor(owner_prefix="user-a_", limit=1)
                self.assertEqual(result["total"], 2)
                self.assertEqual(result["summary"]["completed"], 1)
                self.assertEqual(result["summary"]["failed"], 1)
                self.assertEqual(result["summary"]["running"], 0)
                self.assertEqual(len(result["items"]), 1)
                self.assertTrue(result["items"][0]["thread_id"].startswith("user-a_"))
                self.assertGreaterEqual(result["items"][0]["duration_ms"], 0)
                self.assertEqual(len(store.list_run_monitor(owner_prefix="user-a_", limit=1, offset=1)["items"]), 1)
                self.assertEqual(store.list_run_monitor(owner_prefix="unknown_")["total"], 0)
            finally:
                store.close()

            reopened = LocalSqliteStore(path)
            try:
                self.assertEqual(reopened.list_run_monitor(owner_prefix="user-a_")["total"], 2)
                self.assertEqual(reopened.list_run_monitor(owner_prefix="user-b_")["total"], 1)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
