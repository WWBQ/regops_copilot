from __future__ import annotations

import tempfile
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.backends.open_sandbox import (
    OpenSandboxBackend,
    _seed,
    _snapshot,
    ensure_sandbox_for_thread,
    execution_backend,
    export_project_zip,
)
from agent.store.sqlite_store import LocalSqliteStore


class OpenSandboxBackendTest(unittest.TestCase):
    def tearDown(self) -> None:
        from agent.backends import open_sandbox
        open_sandbox._backends.clear()

    def test_mode_is_explicit(self):
        with patch("agent.backends.open_sandbox.get_env", return_value="opensandbox"):
            self.assertEqual(execution_backend(), "opensandbox")
        with patch("agent.backends.open_sandbox.get_env", return_value="unexpected"):
            with self.assertRaises(ValueError):
                execution_backend()

    def test_snapshot_excludes_secrets_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("print('ok')")
            (root / ".env").write_text("SECRET=hidden")
            (root / "client.pem").write_text("key")
            (root / "link.py").symlink_to(root / "app.py")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "lib.py").write_text("hidden")
            result = _snapshot(root, "/projects/demo")
        self.assertEqual(result, [("/projects/demo/app.py", b"print('ok')")])

    def test_execute_uses_only_sandbox_commands(self):
        run = SimpleNamespace(
            logs=SimpleNamespace(stdout=[SimpleNamespace(text="ok")], stderr=[]),
            exit_code=0,
            error=None,
        )
        sandbox = MagicMock(id="sandbox-1")
        sandbox.commands.run.return_value = run
        backend = OpenSandboxBackend(sandbox)
        result = backend.execute("pwd", timeout=999)
        self.assertEqual(result.output, "ok")
        self.assertEqual(result.exit_code, 0)
        opts = sandbox.commands.run.call_args.kwargs["opts"]
        self.assertEqual(opts.working_directory, "/projects")
        self.assertEqual(opts.timeout.total_seconds(), 300)

    def test_file_transfer_uses_remote_filesystem(self):
        sandbox = MagicMock(id="sandbox-1")
        sandbox.files.read_bytes.return_value = b"hello"
        backend = OpenSandboxBackend(sandbox)
        uploaded = backend.upload_files([("/projects/demo/main.py", b"hello")])
        downloaded = backend.download_files(["/projects/demo/main.py"])
        self.assertIsNone(uploaded[0].error)
        self.assertEqual(downloaded[0].content, b"hello")
        self.assertEqual(sandbox.files.write_files.call_count, 1)
        self.assertEqual(sandbox.files.write_files.call_args.args[0][0].mode, 644)
        sandbox.files.read_bytes.assert_called_once_with("/projects/demo/main.py")

    def test_seed_uses_sdk_permission_digits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "demo"
            project.mkdir(parents=True)
            (project / "main.py").write_text("print(42)")
            (root / "skills").mkdir()
            sandbox = MagicMock()
            sandbox.commands.run.return_value.exit_code = 0
            with patch("agent.backends.open_sandbox.PROJECTS_DIR", root / "projects"), patch(
                "agent.backends.open_sandbox.SKILLS_DIR", root / "skills"
            ):
                _seed(sandbox, "demo")
        entry = sandbox.files.write_files.call_args.args[0][0]
        self.assertEqual(entry.path, "/projects/demo/main.py")
        self.assertEqual(entry.mode, 644)

    def test_creation_denies_network_and_persists_id(self):
        from agent.backends import open_sandbox

        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t1", "sandbox_id": None, "sandbox_project": "demo"}
        sandbox = MagicMock(id="sandbox-1")
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("agent.backends.open_sandbox._seed") as seed, patch(
            "opensandbox.SandboxSync.create", return_value=sandbox,
        ) as create:
            backend = ensure_sandbox_for_thread("t1")
        self.assertIs(backend.sandbox, sandbox)
        self.assertEqual(create.call_args.kwargs["network_policy"].default_action, "deny")
        self.assertEqual(create.call_args.kwargs["network_policy"].egress, [])
        self.assertNotIn("env", create.call_args.kwargs)
        self.assertNotIn("volumes", create.call_args.kwargs)
        seed.assert_called_once_with(sandbox, "demo")
        store.set_thread_sandbox.assert_called_once_with("t1", sandbox_id="sandbox-1")
        open_sandbox._backends.clear()

    def test_existing_sandbox_failure_does_not_create_local_backend(self):
        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t2", "sandbox_id": "expired"}
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("opensandbox.SandboxSync.connect", side_effect=RuntimeError("gone")), patch(
            "opensandbox.SandboxSync.create",
        ) as create:
            with self.assertRaisesRegex(RuntimeError, "不会新建空沙箱或回退本机"):
                ensure_sandbox_for_thread("t2")
        create.assert_not_called()

    def test_existing_sandbox_reconnects_and_renews(self):
        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t-reconnect", "sandbox_id": "sandbox-old"}
        sandbox = MagicMock(id="sandbox-old")
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("opensandbox.SandboxSync.connect", return_value=sandbox) as connect, patch(
            "opensandbox.SandboxSync.create",
        ) as create:
            backend = ensure_sandbox_for_thread("t-reconnect")
        self.assertIs(backend.sandbox, sandbox)
        self.assertEqual(connect.call_args.args[0], "sandbox-old")
        sandbox.renew.assert_called_once()
        create.assert_not_called()

    def test_thread_binding_survives_sqlite_store_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.sqlite"
            store = LocalSqliteStore(path)
            store.upsert_thread(thread_id="t3", title="demo")
            store.set_thread_sandbox("t3", project_name="demo")
            store.set_thread_sandbox("t3", sandbox_id="sandbox-3")
            with self.assertRaisesRegex(ValueError, "不能在同一会话切换"):
                store.set_thread_sandbox("t3", project_name="other")
            store.close()
            store = LocalSqliteStore(path)
            self.assertEqual(store.get_thread("t3")["sandbox_id"], "sandbox-3")
            self.assertEqual(store.get_thread("t3")["sandbox_project"], "demo")
            store.close()

    def test_coding_graph_does_not_register_host_tools(self):
        from agent.coding.factory import get_coding_agent

        fake_graph = MagicMock()
        fake_graph.with_config.return_value = fake_graph
        config = {"configurable": {
            "thread_id": "thread-graph", "task_kind": "coding", "__is_for_execution__": True,
        }}
        with patch("agent.coding.factory.execution_backend", return_value="opensandbox"), patch(
            "agent.coding.factory.ensure_sandbox_for_thread", return_value=MagicMock(),
        ), patch("agent.coding.factory.make_main_model", return_value=MagicMock()), patch(
            "agent.core.graph.get_checkpointer", return_value=MagicMock(),
        ), patch("agent.coding.factory.create_summarization_tool_middleware", return_value=MagicMock(),
        ), patch("agent.coding.factory.create_deep_agent", return_value=fake_graph) as create:
            self.assertIs(get_coding_agent(config), fake_graph)
        self.assertEqual(create.call_args.kwargs["tools"], [])
        self.assertNotIn("store", create.call_args.kwargs)

    def test_sandbox_mode_bypasses_host_workspace_shortcut(self):
        from agent.core.runtime import run_agent_task

        with patch("agent.core.runtime.execution_backend", return_value="opensandbox"), patch(
            "agent.core.runtime.is_workspace_listing_task", return_value=True,
        ), patch("agent.core.runtime.run_workspace_listing_task") as host_shortcut, patch(
            "agent.core.runtime.classify_task_kind", return_value="coding",
        ), patch("agent.core.runtime.get_store") as get_store, patch(
            "agent.core.runtime.run_plan_response_task", return_value={"status": "completed"},
        ):
            get_store.return_value.get_thread.return_value = None
            result = run_agent_task(
                repo_url=None, prompt="目标项目：/projects/demo\n用户任务：修改测试",
                thread_id="thread-1", allow_financial_audit=False,
            )
        self.assertEqual(result["status"], "completed")
        host_shortcut.assert_not_called()

    def test_export_reads_archive_only_from_sandbox(self):
        store = MagicMock()
        store.get_thread.return_value = {
            "thread_id": "thread-export", "sandbox_id": "sandbox-1", "sandbox_project": "demo",
        }
        sandbox = MagicMock(id="sandbox-1")
        sandbox.commands.run.return_value = SimpleNamespace(exit_code=0)
        sandbox.files.get_file_info.side_effect = lambda paths: {paths[0]: SimpleNamespace(size=3)}
        sandbox.files.read_bytes.return_value = b"ZIP"
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox.ensure_sandbox_for_thread",
            return_value=OpenSandboxBackend(sandbox),
        ):
            project, archive = export_project_zip("thread-export")
        self.assertEqual((project, archive), ("demo", b"ZIP"))
        self.assertEqual(sandbox.commands.run.call_args.args[0][0:2], ["python3", "-c"])
        sandbox.files.delete_files.assert_called_once()

    def test_export_archive_script_excludes_hidden_and_symlink_files(self):
        from agent.backends.open_sandbox import _EXPORT_SCRIPT

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "demo"
            project.mkdir()
            (project / "main.py").write_text("print('ok')")
            (project / ".env").write_text("SECRET=hidden")
            (project / "shortcut.py").symlink_to(project / "main.py")
            archive = base / "result.zip"
            completed = subprocess.run(
                [sys.executable, "-c", _EXPORT_SCRIPT, "demo", str(archive), str(base)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(package.namelist(), ["demo/main.py"])


if __name__ == "__main__":
    unittest.main()
