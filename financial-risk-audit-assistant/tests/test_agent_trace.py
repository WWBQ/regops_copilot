import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.core import streaming_runtime
from agent.store.sqlite_store import LocalSqliteStore


class _Stream:
    output = {"messages": []}

    def __iter__(self):
        yield {"method": "messages", "params": {"data": ({"event": "content-block-start", "content": {"type": "text"}}, {})}}
        yield {"method": "messages", "params": {"data": ({"event": "content-block-delta", "delta": {"type": "text-delta", "text": "secret answer"}}, {})}}
        yield {"method": "messages", "params": {"data": ({"event": "content-block-finish", "content": {"type": "text"}}, {})}}
        yield {"method": "tools", "params": {"data": {
            "event": "tool-started", "tool_call_id": "call-1", "tool_name": "lookup_financial_facts",
            "input": {"api_key": "secret-value"},
        }}}
        yield {"method": "tools", "params": {"data": {
            "event": "tool-finished", "tool_call_id": "call-1", "output": "secret tool output",
        }}}


class _Agent:
    def stream_events(self, *_args, **_kwargs):
        return _Stream()


class _FailingStream:
    def __iter__(self):
        yield {"method": "tools", "params": {"data": {
            "event": "tool-started", "tool_call_id": "call-2", "tool_name": "search_report_evidence",
        }}}
        raise RuntimeError("upstream failed")


class _FailingAgent:
    def stream_events(self, *_args, **_kwargs):
        return _FailingStream()


class AgentTraceTest(unittest.TestCase):
    def test_failure_closes_open_tool_span(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalSqliteStore(Path(directory) / "store.sqlite")
            try:
                store.upsert_thread(thread_id="owner_thread", title="risk")
                store.record_run(run_id="run-2", thread_id="owner_thread", status="running")
                with patch.object(streaming_runtime, "get_store", return_value=store), \
                     patch.object(streaming_runtime, "record_event"):
                    with self.assertRaisesRegex(RuntimeError, "upstream failed"):
                        streaming_runtime.run_agent_with_event_stream(
                            agent=_FailingAgent(), thread_id="owner_thread", run_id="run-2",
                            content="input", model_id="qwen3.8-max",
                        )
                events = store.get_agent_run_trace(run_id="run-2", owner_prefix="owner_")["events"]
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["status"], "failed")
                self.assertIsNotNone(events[0]["finished_at"])
            finally:
                store.close()

    def test_raw_stream_records_safe_model_and_tool_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalSqliteStore(Path(directory) / "store.sqlite")
            try:
                store.upsert_thread(thread_id="owner_thread", title="risk")
                store.record_run(run_id="run-1", thread_id="owner_thread", status="running")
                with patch.object(streaming_runtime, "get_store", return_value=store), \
                     patch.object(streaming_runtime, "record_event"):
                    streaming_runtime.run_agent_with_event_stream(
                        agent=_Agent(), thread_id="owner_thread", run_id="run-1",
                        content="augmented prompt secret", model_id="qwen3.8-max",
                        user_preview="检查 2024 年风险", task_kind="financial_audit",
                    )
                trace = store.get_agent_run_trace(run_id="run-1", owner_prefix="owner_")
                events = trace["events"]
                self.assertEqual([item["phase"] for item in events], ["user", "model", "tool"])
                self.assertEqual(events[-1]["status"], "completed")
                labels = " ".join(item["label"] for item in events)
                self.assertIn("lookup_financial_facts", labels)
                self.assertIn("qwen3.8-max", labels)
                self.assertNotIn("secret", labels)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
