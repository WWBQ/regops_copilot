from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.backends.coding_snapshot_memory import forget_snapshot, recall_snapshot, remember_snapshot
from agent.backends.open_sandbox import LazyOpenSandboxBackend, OpenSandboxBackend
from agent.backends.open_sandbox import _load_snapshot


USER = "00000000-0000-0000-0000-000000000001"
THREAD = f"{USER}_coding_11111111-1111-1111-1111-111111111111"
OTHER = f"{USER}_coding_22222222-2222-2222-2222-222222222222"
URI = f"object://regops-docs/coding-snapshots/{THREAD}.zip"


class CodingSnapshotMemoryTest(unittest.TestCase):
    def test_reference_is_scoped_to_user_and_conversation(self):
        values: dict[tuple[tuple[str, ...], str], dict[str, str]] = {}
        store = MagicMock()
        store.put.side_effect = lambda namespace, key, value: values.__setitem__((namespace, key), value)
        store.get.side_effect = lambda namespace, key: (
            SimpleNamespace(value=values[(namespace, key)]) if (namespace, key) in values else None
        )
        store.delete.side_effect = lambda namespace, key: values.pop((namespace, key), None)
        with patch("agent.core.graph.get_langgraph_store", return_value=store):
            remember_snapshot(THREAD, uri=URI, sha256=hashlib.sha256(b"zip").hexdigest())
            self.assertEqual(recall_snapshot(THREAD)["object_uri"], URI)
            self.assertIsNone(recall_snapshot(OTHER))
            forget_snapshot(THREAD)
            self.assertIsNone(recall_snapshot(THREAD))
        self.assertEqual(store.put.call_args.args[0], ("ai-coding", "snapshots", USER))

    def test_rejects_cross_thread_object_reference(self):
        wrong_uri = f"object://regops-docs/coding-snapshots/{OTHER}.zip"
        with patch("agent.core.graph.get_langgraph_store") as store:
            with self.assertRaisesRegex(ValueError, "不属于当前会话"):
                remember_snapshot(THREAD, uri=wrong_uri, sha256="a" * 64)
            store.return_value.put.assert_not_called()

    def test_lazy_backend_does_not_connect_until_file_or_command_tool(self):
        sandbox = MagicMock(id="sandbox-new")
        sandbox.commands.run.return_value = SimpleNamespace(
            logs=SimpleNamespace(stdout=[SimpleNamespace(text="ok")], stderr=[]),
            exit_code=0, error=None,
        )
        with patch("agent.backends.open_sandbox.ensure_sandbox_for_thread", return_value=OpenSandboxBackend(sandbox)) as ensure:
            backend = LazyOpenSandboxBackend(THREAD)
            self.assertEqual(backend.get_work_dir(), "/projects")
            self.assertEqual(backend.id, THREAD)
            ensure.assert_not_called()
            self.assertEqual(backend.execute("pwd").output, "ok")
            ensure.assert_called_once_with(THREAD)

    def test_remembered_snapshot_is_hash_checked_before_restore(self):
        payload = b"zip content"
        reference = {"object_uri": URI, "sha256": hashlib.sha256(payload).hexdigest()}
        with patch("agent.backends.open_sandbox.recall_snapshot", return_value=reference), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=payload,
        ):
            self.assertEqual(_load_snapshot(THREAD), payload)
        with patch("agent.backends.open_sandbox.recall_snapshot", return_value=reference), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=b"other",
        ):
            with self.assertRaisesRegex(RuntimeError, "哈希不一致"):
                _load_snapshot(THREAD)
        with patch("agent.backends.open_sandbox.recall_snapshot", return_value=reference), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=None,
        ):
            with self.assertRaisesRegex(RuntimeError, "快照已丢失"):
                _load_snapshot(THREAD)


if __name__ == "__main__":
    unittest.main()
