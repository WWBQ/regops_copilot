from __future__ import annotations

import tempfile
import io
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
    save_export_snapshot,
    SandboxExpiredError,
    consume_workspace_notice,
)
from agent.store.sqlite_store import LocalSqliteStore


class OpenSandboxBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.memory_read = patch("agent.backends.open_sandbox.recall_snapshot", return_value=None)
        self.memory_write = patch("agent.backends.open_sandbox.remember_snapshot")
        self.memory_read.start()
        self.memory_write.start()

    def tearDown(self) -> None:
        from agent.backends import open_sandbox
        open_sandbox._backends.clear()
        open_sandbox._workspace_notices.clear()
        self.memory_write.stop()
        self.memory_read.stop()

    def test_mode_is_explicit(self):
        with patch("agent.backends.open_sandbox.get_env", return_value="opensandbox"):
            self.assertEqual(execution_backend(), "opensandbox")
        with patch("agent.backends.open_sandbox.get_env", return_value="unexpected"):
            with self.assertRaises(RuntimeError):
                execution_backend()
        with patch("agent.backends.open_sandbox.get_env", return_value="local"):
            with self.assertRaisesRegex(RuntimeError, "不会回退到本机"):
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

    def test_seed_only_copies_static_skills_not_host_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "projects" / "demo"
            project.mkdir(parents=True)
            (project / "main.py").write_text("print(42)")
            skill = root / "skills" / "ai-coding-implementation"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("Skill content")
            sandbox = MagicMock()
            sandbox.commands.run.return_value.exit_code = 0
            with patch("agent.backends.open_sandbox.SKILLS_DIR", root / "skills"):
                _seed(sandbox)
        entry = sandbox.files.write_files.call_args.args[0][0]
        self.assertEqual(entry.path, "/skills/ai-coding-implementation/SKILL.md")
        self.assertEqual(entry.mode, 644)
        self.assertNotIn("/projects/demo", sandbox.commands.run.call_args.args[0])

    def test_seed_creates_empty_sandbox_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projects" / "empty").mkdir(parents=True)
            (root / "skills").mkdir()
            sandbox = MagicMock()
            sandbox.commands.run.return_value.exit_code = 0
            with patch("agent.backends.open_sandbox.SKILLS_DIR", root / "skills"):
                _seed(sandbox)
        self.assertIn("/projects", sandbox.commands.run.call_args.args[0])
        self.assertNotIn("/projects/empty", sandbox.commands.run.call_args.args[0])
        sandbox.files.write_files.assert_not_called()

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
        seed.assert_called_once_with(sandbox)
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

    def test_missing_sandbox_without_snapshot_creates_empty_workspace(self):
        from opensandbox.exceptions import SandboxApiException

        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t-expired", "sandbox_id": "missing"}
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("opensandbox.SandboxSync.connect", side_effect=SandboxApiException("not found", status_code=404)), patch(
            "agent.backends.open_sandbox._load_snapshot", return_value=None,
        ), patch("opensandbox.SandboxSync.create", return_value=MagicMock(id="new")) as create, patch(
            "agent.backends.open_sandbox._seed",
        ):
            ensure_sandbox_for_thread("t-expired")
        create.assert_called_once()
        self.assertIn("空沙箱", consume_workspace_notice("t-expired"))

    def test_expired_sandbox_restores_object_snapshot_before_rebinding(self):
        from opensandbox.exceptions import SandboxApiException

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as package:
            package.writestr("workspace/demo/main.py", "print(1)")
        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t-restore", "sandbox_id": "old", "sandbox_project": None}
        sandbox = MagicMock(id="new")
        sandbox.commands.run.return_value.exit_code = 0
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("opensandbox.SandboxSync.connect", side_effect=SandboxApiException("gone", status_code=404)), patch(
            "opensandbox.SandboxSync.create", return_value=sandbox,
        ) as create, patch("agent.backends.open_sandbox._seed"), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=payload.getvalue(),
        ), patch("agent.backends.open_sandbox.put_snapshot", return_value="object://regops-docs/coding-snapshots/t-restore.zip",
        ):
            backend = ensure_sandbox_for_thread("t-restore")
        self.assertIs(backend.sandbox, sandbox)
        self.assertEqual(create.call_args.kwargs["network_policy"].default_action, "deny")
        written = sandbox.files.write_files.call_args.args[0][0]
        self.assertEqual((written.path, written.data), ("/projects/demo/main.py", b"print(1)"))
        store.set_thread_sandbox.assert_called_once_with("t-restore", sandbox_id="new")

    def test_invalid_restored_path_destroys_new_sandbox(self):
        from opensandbox.exceptions import SandboxApiException

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as package:
            package.writestr("workspace/../escape", "bad")
        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t-invalid", "sandbox_id": "old", "sandbox_project": None}
        sandbox = MagicMock(id="new")
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("opensandbox.SandboxSync.connect", side_effect=SandboxApiException("gone", status_code=404)), patch(
            "opensandbox.SandboxSync.create", return_value=sandbox,
        ), patch("agent.backends.open_sandbox._seed"), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=payload.getvalue(),
        ), patch("agent.backends.open_sandbox.put_snapshot", return_value="object://regops-docs/coding-snapshots/t-invalid.zip",
        ):
            with self.assertRaisesRegex(RuntimeError, "不安全"):
                ensure_sandbox_for_thread("t-invalid")
        sandbox.destroy.assert_called_once()
        store.set_thread_sandbox.assert_not_called()

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
            "agent.backends.open_sandbox.ensure_sandbox_for_thread",
        ) as ensure, patch("agent.coding.factory.make_main_model", return_value=MagicMock()), patch(
            "agent.core.graph.get_checkpointer", return_value=MagicMock(),
        ), patch("agent.coding.factory.create_summarization_tool_middleware", return_value=MagicMock(),
        ), patch("agent.coding.factory.create_deep_agent", return_value=fake_graph) as create:
            self.assertIs(get_coding_agent(config), fake_graph)
        self.assertEqual(create.call_args.kwargs["tools"], [])
        self.assertNotIn("store", create.call_args.kwargs)
        ensure.assert_not_called()

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
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as package:
            package.writestr("workspace/demo/main.py", "print(1)")
        payload = archive_buffer.getvalue()
        store = MagicMock()
        store.get_thread.return_value = {
            "thread_id": "thread-export", "sandbox_id": "sandbox-1", "sandbox_project": "demo",
        }
        sandbox = MagicMock(id="sandbox-1")
        sandbox.commands.run.return_value = SimpleNamespace(exit_code=0)
        sandbox.files.get_file_info.side_effect = lambda paths: {paths[0]: SimpleNamespace(size=len(payload))}
        sandbox.files.read_bytes.return_value = payload
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox.ensure_sandbox_for_thread",
            return_value=OpenSandboxBackend(sandbox),
        ), patch("agent.backends.open_sandbox.get_snapshot", return_value=None), patch(
            "agent.backends.open_sandbox.put_snapshot"
        ):
            project, archive = export_project_zip("thread-export")
        self.assertEqual((project, archive), ("workspace", payload))
        self.assertEqual(sandbox.commands.run.call_args.args[0][0:2], ["python3", "-c"])
        self.assertEqual(sandbox.commands.run.call_args.args[0][3], "")
        sandbox.files.delete_files.assert_called_once()

    def test_default_workspace_can_be_exported(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as package:
            package.writestr("workspace/main.py", "print(1)")
        payload = archive_buffer.getvalue()
        store = MagicMock()
        store.get_thread.return_value = {
            "thread_id": "thread-default", "sandbox_id": "sandbox-1", "sandbox_project": None,
        }
        sandbox = MagicMock(id="sandbox-1")
        sandbox.commands.run.return_value = SimpleNamespace(exit_code=0)
        sandbox.files.get_file_info.side_effect = lambda paths: {paths[0]: SimpleNamespace(size=len(payload))}
        sandbox.files.read_bytes.return_value = payload
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox.ensure_sandbox_for_thread",
            return_value=OpenSandboxBackend(sandbox),
        ), patch("agent.backends.open_sandbox.get_snapshot", return_value=None), patch(
            "agent.backends.open_sandbox.put_snapshot"
        ):
            project, archive = export_project_zip("thread-default")
        self.assertEqual((project, archive), ("workspace", payload))
        self.assertEqual(sandbox.commands.run.call_args.args[0][3], "")

    def test_empty_sandbox_does_not_save_or_offer_empty_export(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w"):
            pass
        with patch("agent.backends.open_sandbox._archive_from_sandbox", return_value=("workspace", archive_buffer.getvalue())), patch(
            "agent.backends.open_sandbox.put_snapshot",
        ) as put:
            self.assertFalse(save_export_snapshot("thread-empty"))
            put.assert_not_called()
        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "thread-empty", "sandbox_id": "sandbox-1"}
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=None,
        ), patch("agent.backends.open_sandbox._archive_from_sandbox", return_value=("workspace", archive_buffer.getvalue())):
            with self.assertRaisesRegex(ValueError, "没有可导出"):
                export_project_zip("thread-empty")

    def test_new_workspace_snapshot_restores_despite_legacy_project_name(self):
        from agent.backends.open_sandbox import _checked_files

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as package:
            package.writestr("workspace/main.py", "print(1)")
        self.assertEqual(_checked_files(archive_buffer.getvalue(), "calculator"), [("/projects/main.py", b"print(1)")])

        old_buffer = io.BytesIO()
        with zipfile.ZipFile(old_buffer, "w") as package:
            package.writestr("calculator/main.py", "print(2)")
        self.assertEqual(_checked_files(old_buffer.getvalue(), "calculator"), [("/projects/calculator/main.py", b"print(2)")])

    def test_export_script_reads_workspace_root_with_legacy_project_absent(self):
        from agent.backends.open_sandbox import _EXPORT_SCRIPT

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("print(1)")
            archive_path = root.parent / f"{root.name}-export.zip"
            try:
                result = subprocess.run(
                    [sys.executable, "-c", _EXPORT_SCRIPT, "", str(archive_path), str(root)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                with zipfile.ZipFile(archive_path) as package:
                    self.assertEqual(package.namelist(), ["workspace/main.py"])
            finally:
                archive_path.unlink(missing_ok=True)

    def test_missing_old_code_is_not_exported_as_empty_zip(self):
        from agent.backends import open_sandbox

        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "thread-lost", "sandbox_id": "expired"}
        sandbox = MagicMock(id="new-empty")
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=None,
        ), patch("agent.backends.open_sandbox.ensure_sandbox_for_thread", return_value=OpenSandboxBackend(sandbox)):
            open_sandbox._workspace_notices["thread-lost"] = "空沙箱"
            with self.assertRaisesRegex(SandboxExpiredError, "不能将其作为旧代码导出"):
                export_project_zip("thread-lost")
        sandbox.commands.run.assert_not_called()

    def test_saved_export_survives_sandbox_expiry(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as package:
            package.writestr("workspace/main.py", "print(1)")
        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "thread-saved", "sandbox_id": "expired"}
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._archive_from_sandbox", return_value=("workspace", archive_buffer.getvalue()),
        ) as build, patch("agent.backends.open_sandbox.put_snapshot") as put, patch(
            "agent.backends.open_sandbox.get_snapshot", return_value=archive_buffer.getvalue(),
        ):
            save_export_snapshot("thread-saved")
            put.assert_called_once_with("thread-saved", archive_buffer.getvalue())
            build.assert_called_once_with("thread-saved")
            with patch("agent.backends.open_sandbox.ensure_sandbox_for_thread") as connect:
                project, archive = export_project_zip("thread-saved")
            connect.assert_not_called()
            self.assertEqual(project, "workspace")
            self.assertEqual(archive, archive_buffer.getvalue())

    def test_legacy_local_export_is_migrated_to_object_store(self):
        from agent.backends import open_sandbox

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as package:
            package.writestr("workspace/main.py", "print(1)")
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "thread-old.zip"
            legacy.write_bytes(archive_buffer.getvalue())
            with patch.object(open_sandbox, "_LEGACY_EXPORT_DIR", Path(tmp)), patch(
                "agent.backends.open_sandbox.get_snapshot", return_value=None,
            ), patch("agent.backends.open_sandbox.put_snapshot") as upload:
                self.assertEqual(open_sandbox._load_snapshot("thread-old"), archive_buffer.getvalue())
            upload.assert_called_once_with("thread-old", archive_buffer.getvalue())

    def test_storage_unavailable_does_not_create_empty_sandbox(self):
        from opensandbox.exceptions import SandboxApiException

        store = MagicMock()
        store.get_thread.return_value = {"thread_id": "t-offline", "sandbox_id": "old"}
        with patch("agent.core.graph.get_store", return_value=store), patch(
            "agent.backends.open_sandbox._connection_config", return_value=object(),
        ), patch("opensandbox.SandboxSync.connect", side_effect=SandboxApiException("gone", status_code=404)), patch(
            "agent.backends.open_sandbox.get_snapshot", side_effect=RuntimeError("store unavailable"),
        ), patch("opensandbox.SandboxSync.create") as create:
            with self.assertRaisesRegex(RuntimeError, "store unavailable"):
                ensure_sandbox_for_thread("t-offline")
        create.assert_not_called()

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

    def test_default_workspace_archive_contains_new_projects_only(self):
        from agent.backends.open_sandbox import _EXPORT_SCRIPT

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "projects"
            (root / "fresh").mkdir(parents=True)
            (root / "fresh" / "main.py").write_text("print('ok')")
            (root / ".env").write_text("SECRET=hidden")
            archive = Path(tmp) / "result.zip"
            completed = subprocess.run(
                [sys.executable, "-c", _EXPORT_SCRIPT, "", str(archive), str(root)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(package.namelist(), ["workspace/fresh/main.py"])


if __name__ == "__main__":
    unittest.main()
