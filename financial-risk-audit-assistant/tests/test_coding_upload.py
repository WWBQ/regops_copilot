from __future__ import annotations

import io
import stat
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.backends.coding_upload import UploadRejected, prepare_upload, upload_to_workspace
from agent.backends.open_sandbox import OpenSandboxBackend


def zip_body(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


class CodingUploadTest(unittest.TestCase):
    def test_single_source_file_and_standard_zip(self):
        self.assertEqual(prepare_upload("main.py", b"print(1)"), [("/projects/main.py", b"print(1)")])
        archive = zip_body({"demo/": b"", "demo/main.py": b"print(2)", "demo/README.md": b"hello"})
        self.assertEqual(len(prepare_upload("project.zip", archive)), 2)

    def test_rejects_traversal_credentials_and_file_directory_collision(self):
        for entries in (
            {"../escape.py": b"bad"},
            {"/etc/passwd": b"bad"},
            {"src/.env": b"secret"},
            {"src/.git/config": b"secret"},
            {"a": b"file", "a/b.py": b"child"},
        ):
            with self.subTest(entries=entries), self.assertRaises(UploadRejected):
                prepare_upload("project.zip", zip_body(entries))

    def test_rejects_symlink_zip_entry(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            link = zipfile.ZipInfo("demo/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "/etc/passwd")
        with self.assertRaisesRegex(UploadRejected, "符号链接"):
            prepare_upload("project.zip", output.getvalue())

    def test_upload_uses_remote_sandbox_and_saves_snapshot(self):
        sandbox = MagicMock(id="sandbox-1")
        sandbox.commands.run.return_value = SimpleNamespace(exit_code=0)
        with patch("agent.backends.coding_upload.ensure_sandbox_for_thread", return_value=OpenSandboxBackend(sandbox)), patch(
            "agent.backends.coding_upload.consume_workspace_notice", return_value=None,
        ), patch("agent.backends.coding_upload.save_export_snapshot") as save:
            result = upload_to_workspace("thread-1", "main.py", b"print(1)")
        self.assertEqual(result["file_count"], 1)
        self.assertTrue(result["snapshot_saved"])
        written = sandbox.files.write_files.call_args.args[0][0]
        self.assertEqual((written.path, written.data), ("/projects/main.py", b"print(1)"))
        save.assert_called_once_with("thread-1")

    def test_conflict_does_not_write(self):
        sandbox = MagicMock(id="sandbox-1")
        sandbox.commands.run.return_value = SimpleNamespace(exit_code=1)
        with patch("agent.backends.coding_upload.ensure_sandbox_for_thread", return_value=OpenSandboxBackend(sandbox)), patch(
            "agent.backends.coding_upload.save_export_snapshot",
        ) as save:
            with self.assertRaisesRegex(UploadRejected, "目标文件已存在"):
                upload_to_workspace("thread-1", "main.py", b"print(1)")
        sandbox.files.write_files.assert_not_called()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
