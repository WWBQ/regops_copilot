import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.core import events, streaming_runtime
from agent.core.checkpoint_history import latest_checkpoint_todos
from agent.store.sqlite_store import LocalSqliteStore


class _TodoStream:
    output = {"messages": []}

    def __iter__(self):
        yield {"method": "messages", "params": {"data": [{
            "event": "content-block-start", "index": 0,
            "content": {"type": "tool_call_chunk", "name": "write_todos", "id": "call-1"},
        }]}}
        yield {"method": "messages", "params": {"data": [{
            "event": "content-block-delta", "index": 0,
            "delta": {"type": "block-delta", "fields": {
                "type": "tool_call_chunk",
                "args": json.dumps({"todos": [
                    {"content": "检查代码", "status": "in_progress"},
                    {"content": "运行测试", "status": "pending"},
                ]}, ensure_ascii=False),
            }},
        }]}}
        yield {"method": "messages", "params": {"data": [{
            "event": "content-block-finish", "index": 0,
            "content": {"type": "tool_call", "name": "write_todos", "id": "call-1",
                        "args": {"todos": [
                            {"content": "检查代码", "status": "completed"},
                            {"content": "运行测试", "status": "in_progress"},
                        ]}},
        }]}}


class _TodoAgent:
    def stream_events(self, *_args, **_kwargs):
        return _TodoStream()


class TodoEventsTest(unittest.TestCase):
    def test_checkpoint_fallback_reads_todos_state(self):
        checkpoint = {"channel_values": {"todos": [{"content": "检查代码", "status": "completed"}]}}
        with patch("agent.core.checkpoint_history.get_checkpointer") as get_checkpointer:
            get_checkpointer.return_value.get_tuple.return_value.checkpoint = checkpoint
            self.assertEqual(latest_checkpoint_todos("owner_coding_thread"), [
                {"content": "检查代码", "status": "completed"},
            ])

    def test_legacy_tool_call_also_emits_todo_delta(self):
        streamed = []
        tool_call = {"tool_name": "write_todos", "id": "call-legacy", "input": {
            "todos": [{"content": "执行验证", "status": "in_progress"}],
        }}
        with patch.object(streaming_runtime, "record_event") as record:
            result = streaming_runtime._record_write_todos(
                "owner_coding_thread", "run-legacy", tool_call, 1,
                lambda name, data: streamed.append((name, data)),
            )
        self.assertTrue(result)
        record.assert_called_once()
        self.assertEqual(streamed[0][0], "todo_delta")
        self.assertEqual(streamed[0][1]["todos"][0]["content"], "执行验证")

    def test_todo_updates_stream_and_use_same_business_store_as_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalSqliteStore(Path(directory) / "test.sqlite")
            try:
                store.upsert_thread(thread_id="owner_coding_thread", title="coding")
                store.record_run(run_id="run-1", thread_id="owner_coding_thread", status="running")
                streamed = []
                with patch("agent.core.graph.get_store", return_value=store), patch.object(
                    streaming_runtime, "get_store", return_value=store,
                ):
                    streaming_runtime.run_agent_with_event_stream(
                        agent=_TodoAgent(), thread_id="owner_coding_thread", run_id="run-1",
                        content="测试任务", event_sink=lambda name, data: streamed.append((name, data)),
                    )
                updates = [data["todos"] for name, data in streamed if name == "todo_delta"]
                self.assertEqual(len(updates), 2)
                self.assertEqual(updates[-1][0]["status"], "completed")
                saved = [item for item in store.list_run_events("owner_coding_thread") if item["kind"] == "todo"]
                self.assertEqual(len(saved), 1)
                self.assertEqual(json.loads(saved[0]["detail"])["todos"], updates[-1])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
