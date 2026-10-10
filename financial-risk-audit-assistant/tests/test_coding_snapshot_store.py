from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.backends.coding_snapshot_store import delete_snapshot, get_snapshot, put_snapshot


class CodingSnapshotStoreTest(unittest.TestCase):
    def test_put_uses_private_token_and_checks_hash(self):
        body = b"zip-bytes"
        expected = hashlib.sha256(body).hexdigest()
        with patch("agent.backends.coding_snapshot_store.get_env", side_effect=lambda key, default="": {
            "REGOPS_API_BASE_URL": "http://python-ai:8000",
            "REGOPS_SERVICE_TOKEN": "secret",
        }.get(key, default)), patch(
            "agent.backends.coding_snapshot_store.requests.put",
            return_value=SimpleNamespace(status_code=200, json=lambda: {"sha256": expected, "object_uri": "object://regops-docs/coding-snapshots/thread_1.zip"}),
        ) as send:
            uri = put_snapshot("thread_1", body)
        self.assertEqual(uri, "object://regops-docs/coding-snapshots/thread_1.zip")
        self.assertEqual(send.call_args.args[0], "http://python-ai:8000/internal/coding-snapshots/thread_1")
        self.assertEqual(send.call_args.kwargs["headers"]["X-Regops-Service-Token"], "secret")
        self.assertEqual(send.call_args.kwargs["data"], body)

    def test_missing_snapshot_differs_from_storage_failure(self):
        with patch("agent.backends.coding_snapshot_store.get_env", side_effect=lambda key, default="": {
            "REGOPS_API_BASE_URL": "http://python-ai:8000",
            "REGOPS_SERVICE_TOKEN": "secret",
        }.get(key, default)), patch(
            "agent.backends.coding_snapshot_store.requests.get",
            return_value=SimpleNamespace(status_code=404),
        ):
            self.assertIsNone(get_snapshot("thread_1"))
        with patch("agent.backends.coding_snapshot_store.get_env", side_effect=lambda key, default="": {
            "REGOPS_API_BASE_URL": "http://python-ai:8000",
            "REGOPS_SERVICE_TOKEN": "secret",
        }.get(key, default)), patch(
            "agent.backends.coding_snapshot_store.requests.get",
            return_value=SimpleNamespace(status_code=503),
        ):
            with self.assertRaisesRegex(RuntimeError, "503"):
                get_snapshot("thread_1")

    def test_invalid_id_never_calls_http(self):
        with patch("agent.backends.coding_snapshot_store.requests.delete") as send:
            with self.assertRaises(ValueError):
                delete_snapshot("../other-user")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
