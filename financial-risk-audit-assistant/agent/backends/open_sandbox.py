"""OpenSandbox-backed DeepAgents execution for AI Coding only.

AI Coding project files are created only inside the sandbox. Bundled Skills are
seeded once per thread; no host project directory or credential is mounted.
"""

from __future__ import annotations

import os
import re
import stat
import threading
import uuid
import io
import hashlib
import zipfile
from datetime import timedelta
from pathlib import Path

from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox

from agent.core.settings import DATA_DIR, SKILLS_DIR
from agent.env_utils import get_env
from agent.backends.coding_snapshot_store import delete_snapshot, get_snapshot, put_snapshot
from agent.backends.coding_snapshot_memory import forget_snapshot, recall_snapshot, remember_snapshot

_lock = threading.RLock()
_backends: dict[str, OpenSandboxBackend] = {}
_workspace_notices: dict[str, str] = {}
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".secrets", "dist", "build"}
_SKIP_FILES = {
    ".env", ".env.local", ".env.production", ".npmrc", ".pypirc",
    ".git-credentials", "credentials.json", "id_rsa", "id_ed25519",
}
_SKIP_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"}
_MAX_FILES = 2000
_MAX_BYTES = 20 * 1024 * 1024
_LEGACY_EXPORT_DIR = DATA_DIR / "coding_exports"


class SandboxExpiredError(RuntimeError):
    """The remote sandbox no longer exists and cannot supply unsaved files."""


def execution_backend() -> str:
    mode = get_env("AI_CODING_EXECUTION_BACKEND", "opensandbox").strip().lower()
    if mode != "opensandbox":
        raise RuntimeError("AI Coding 仅支持 OpenSandbox；不会回退到本机执行")
    return "opensandbox"


def _connection_config():
    from opensandbox.config.connection_sync import ConnectionConfigSync

    domain = get_env("AI_CODING_SANDBOX_DOMAIN", "").strip()
    api_key = get_env("AI_CODING_SANDBOX_API_KEY", "").strip()
    if not domain or not api_key:
        raise RuntimeError("OpenSandbox 未配置 AI_CODING_SANDBOX_DOMAIN / AI_CODING_SANDBOX_API_KEY")
    return ConnectionConfigSync(
        domain=domain,
        api_key=api_key,
        protocol=get_env("AI_CODING_SANDBOX_PROTOCOL", "http").strip(),
        use_server_proxy=True,
        # A cold Kubernetes sandbox may need to pull a multi-GB image first.
        request_timeout=timedelta(seconds=180),
    )


def _snapshot(root: Path, destination: str) -> list[tuple[str, bytes]]:
    """Build a bounded, symlink-free snapshot before writing any sandbox files."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("项目目录不存在或是符号链接")
    root = root.resolve()
    files: list[tuple[str, bytes]] = []
    total = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".") and not (Path(current) / d).is_symlink()]
        for name in names:
            path = Path(current) / name
            if (path.is_symlink() or name in _SKIP_FILES or
                    (name.startswith(".") and name not in {".gitignore", ".editorconfig"}) or
                    path.suffix.lower() in _SKIP_SUFFIXES):
                continue
            if not path.is_file() or path.stat().st_nlink > 1:
                continue
            relative = path.relative_to(root)
            if any(part in _SKIP_DIRS for part in relative.parts):
                continue
            size = path.stat().st_size
            total += size
            if len(files) >= _MAX_FILES or total > _MAX_BYTES:
                raise ValueError("项目快照超过 2000 个文件或 20 MiB；请缩小项目后重试")
            files.append((f"{destination}/{relative.as_posix()}", path.read_bytes()))
    return files


def _seed(sandbox) -> None:
    from opensandbox.models.filesystem import WriteEntry

    snapshots: list[tuple[str, bytes]] = []
    for skill_name in ("ai-coding-implementation", "repo-bootstrap-analysis", "code-review"):
        skill = SKILLS_DIR / skill_name
        if skill.is_dir():
            snapshots.extend(_snapshot(skill, f"/skills/{skill_name}"))
    folders = {"/projects", "/skills", "/tmp"}
    for path, _ in snapshots:
        parent = Path(path).parent
        while str(parent) not in {"/", "."}:
            folders.add(str(parent))
            parent = parent.parent
    result = sandbox.commands.run(["mkdir", "-p", *sorted(folders)])
    if result.exit_code != 0:
        raise RuntimeError("OpenSandbox 工作目录初始化失败")
    for start in range(0, len(snapshots), 50):
        sandbox.files.write_files([
            WriteEntry(path=path, data=data, mode=644)
            for path, data in snapshots[start:start + 50]
        ])


class OpenSandboxBackend(BaseSandbox):
    def __init__(self, sandbox):
        self.sandbox = sandbox

    @property
    def id(self) -> str:
        return str(self.sandbox.id)

    def get_work_dir(self) -> str:
        return "/projects"

    def get_workspace_root(self) -> str:
        return "/"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        from opensandbox.models.execd import RunCommandOpts

        # Timeout belongs to the sandbox API, never to subprocess on the host.
        bounded = min(max(int(timeout or 120), 1), 300)
        try:
            run = self.sandbox.commands.run(
                command,
                opts=RunCommandOpts(working_directory="/projects", timeout=timedelta(seconds=bounded)),
            )
            stdout = "".join(item.text for item in run.logs.stdout)
            stderr = "".join(item.text for item in run.logs.stderr)
            output = (stdout + ("\n" if stdout and stderr else "") + stderr)
            if run.error is not None:
                output = (output + "\n" + str(run.error.value)).strip()
            truncated = len(output) > 65536
            code = run.exit_code if run.exit_code is not None else (1 if run.error is not None else 0)
            return ExecuteResponse(output=output[:65536], exit_code=code, truncated=truncated)
        except Exception as exc:
            raise RuntimeError("OpenSandbox 命令执行失败；未回退到本机 Shell") from exc

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        from opensandbox.models.filesystem import WriteEntry

        responses = []
        for path, content in files:
            try:
                self.sandbox.files.write_files([WriteEntry(path=path, data=content, mode=644)])
                responses.append(FileUploadResponse(path=path))
            except Exception as exc:
                responses.append(FileUploadResponse(path=path, error=str(exc)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            try:
                responses.append(FileDownloadResponse(path=path, content=self.sandbox.files.read_bytes(path)))
            except Exception as exc:
                responses.append(FileDownloadResponse(path=path, error=str(exc)))
        return responses


class LazyOpenSandboxBackend(BaseSandbox):
    """Resolve a thread's sandbox only on its first actual file/command operation."""

    def __init__(self, thread_id: str):
        self.thread_id = thread_id

    @property
    def id(self) -> str:
        return self.thread_id

    def get_work_dir(self) -> str:
        return "/projects"

    def get_workspace_root(self) -> str:
        return "/"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return ensure_sandbox_for_thread(self.thread_id).execute(command, timeout=timeout)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return ensure_sandbox_for_thread(self.thread_id).upload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return ensure_sandbox_for_thread(self.thread_id).download_files(paths)


def consume_workspace_notice(thread_id: str) -> str | None:
    with _lock:
        return _workspace_notices.pop(thread_id, None)


def ensure_sandbox_for_thread(thread_id: str) -> OpenSandboxBackend:
    from opensandbox import SandboxSync
    from opensandbox.exceptions import SandboxApiException
    from opensandbox.models.sandboxes import NetworkPolicy
    from agent.core.graph import get_store

    with _lock:
        if thread_id in _backends:
            backend = _backends[thread_id]
            try:
                backend.sandbox.renew(timedelta(minutes=60))
            except Exception as exc:
                _backends.pop(thread_id, None)
                if not isinstance(exc, SandboxApiException) or exc.status_code != 404:
                    raise RuntimeError("原 OpenSandbox 续期失败；未回退本机执行") from exc
            else:
                return backend
        store = get_store()
        thread = store.get_thread(thread_id)
        if thread is None:
            raise RuntimeError("AI Coding 会话不存在")
        config = _connection_config()
        sandbox_id = thread.get("sandbox_id")
        archive_to_restore: bytes | None = None
        lost_workspace = False
        if sandbox_id:
            try:
                sandbox = SandboxSync.connect(str(sandbox_id), connection_config=config)
                sandbox.renew(timedelta(minutes=60))
            except Exception as exc:
                if not isinstance(exc, SandboxApiException) or exc.status_code != 404:
                    raise RuntimeError("原 OpenSandbox 不可用；不会新建空沙箱或回退本机") from exc
                archive_to_restore = _load_snapshot(thread_id)
                if archive_to_restore is None:
                    lost_workspace = True
                sandbox_id = None
        if not sandbox_id:
            if archive_to_restore is None and not lost_workspace:
                if recall_snapshot(thread_id) is not None:
                    archive_to_restore = _load_snapshot(thread_id)
                elif thread.get("latest_run_status") == "completed":
                    lost_workspace = True
            try:
                sandbox = SandboxSync.create(
                    image=get_env("AI_CODING_SANDBOX_IMAGE", "opensandbox/code-interpreter:v1.1.0"),
                    timeout=timedelta(minutes=60),
                    resource={"cpu": "1", "memory": "2Gi"},
                    network_policy=NetworkPolicy(defaultAction="deny", egress=[]),
                    connection_config=config,
                    metadata={"component": "ai-coding"},
                )
            except Exception as exc:
                raise RuntimeError("OpenSandbox 创建失败；未回退到本机 Shell") from exc
            try:
                _seed(sandbox)
                if archive_to_restore is not None:
                    _restore_snapshot(sandbox, archive_to_restore, thread.get("sandbox_project"))
                store.set_thread_sandbox(thread_id, sandbox_id=str(sandbox.id))
                if lost_workspace:
                    _workspace_notices[thread_id] = (
                        "当前会话没有可恢复的代码快照；已创建空沙箱。"
                        "历史对话仍在，但旧文件（若有）不可用。"
                    )
            except Exception:
                sandbox.destroy()
                raise
        backend = OpenSandboxBackend(sandbox)
        _backends[thread_id] = backend
        return backend


def destroy_sandbox_for_thread(thread_id: str) -> None:
    from opensandbox import SandboxSync
    from opensandbox.exceptions import SandboxApiException
    from agent.core.graph import get_store

    with _lock:
        thread = get_store().get_thread(thread_id)
        if not thread or not thread.get("sandbox_id"):
            return
        backend = _backends.pop(thread_id, None)
        try:
            sandbox = backend.sandbox if backend else SandboxSync.connect(
                str(thread["sandbox_id"]), connection_config=_connection_config(),
            )
            sandbox.destroy()
        except SandboxApiException as exc:
            if exc.status_code != 404:
                raise
            # An expired instance is already gone; the conversation may be deleted.


_EXPORT_SCRIPT = r"""
import os, pathlib, sys, zipfile
project = sys.argv[1]
output = sys.argv[2]
root = pathlib.Path(sys.argv[3]) / project if project else pathlib.Path(sys.argv[3])
if not root.is_dir() or root.is_symlink():
    raise SystemExit('project missing')
count = 0
total = 0
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', 'venv', 'dist', 'build'} and not (pathlib.Path(current) / d).is_symlink()]
        for name in names:
            path = pathlib.Path(current) / name
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink > 1 or name in {'.env', '.env.local', '.env.production', '.npmrc', '.pypirc', '.git-credentials', 'credentials.json', 'id_rsa', 'id_ed25519'} or (name.startswith('.') and name not in {'.gitignore', '.editorconfig'}) or path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.sqlite', '.db'}:
                continue
            count += 1
            total += path.stat().st_size
            if count > 2000 or total > 20 * 1024 * 1024:
                raise SystemExit('export exceeds size or file limit')
            archive.write(path, arcname=f'{project or "workspace"}/{path.relative_to(root).as_posix()}')
"""


def _legacy_saved_export_path(thread_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        raise ValueError("会话 ID 无效")
    return _LEGACY_EXPORT_DIR / f"{thread_id}.zip"


def _checked_files(archive: bytes, project_name: str | None) -> list[tuple[str, bytes]]:
    """Validate an untrusted archive before any sandbox file is written."""
    if len(archive) > _MAX_BYTES or not zipfile.is_zipfile(io.BytesIO(archive)):
        raise RuntimeError("对象存储中的沙箱快照不是有效 ZIP")
    # New snapshots always cover /projects. Older snapshots were nested under
    # the thread's sandbox_project; keep both formats readable during restore.
    prefix = project_name or "workspace"
    files: list[tuple[str, bytes]] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        members = package.infolist()
        if len(members) > _MAX_FILES:
            raise RuntimeError("沙箱快照文件数量超过上限")
        if project_name and members and members[0].filename.split("/", 1)[0] == "workspace":
            prefix = "workspace"
        for member in members:
            parts = member.filename.split("/")
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (member.is_dir() or member.flag_bits & 1 or file_type not in {0, stat.S_IFREG}
                    or member.filename.startswith("/") or "\\" in member.filename
                    or any(part in {"", ".", ".."} for part in parts)
                    or parts[0] != prefix or len(parts) < 2):
                raise RuntimeError("沙箱快照包含不安全的文件路径")
            total += member.file_size
            if total > _MAX_BYTES:
                raise RuntimeError("沙箱快照解压大小超过上限")
            relative = parts[1:] if prefix == "workspace" else parts
            try:
                data = package.read(member)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise RuntimeError("沙箱快照校验失败") from exc
            files.append(("/projects/" + "/".join(relative), data))
    return files


def _load_snapshot(thread_id: str) -> bytes | None:
    remembered = recall_snapshot(thread_id)
    archive = get_snapshot(thread_id)
    if archive is not None:
        digest = hashlib.sha256(archive).hexdigest()
        if remembered is not None and digest != remembered["sha256"]:
            raise RuntimeError("对象存储快照与长期记忆哈希不一致，拒绝恢复")
        if remembered is None:
            # Adopt snapshots written by the earlier object-store implementation.
            _persist_snapshot(thread_id, archive)
        return archive
    if remembered is not None:
        raise RuntimeError("长期记忆指向的代码快照已丢失，未创建空沙箱以免覆盖旧代码")
    # One-time migration for archives saved by the previous local implementation.
    old = _legacy_saved_export_path(thread_id)
    if not old.is_file() or old.is_symlink():
        return None
    if old.stat().st_size > _MAX_BYTES:
        raise RuntimeError("旧版沙箱快照超过 20 MiB")
    archive = old.read_bytes()
    if not zipfile.is_zipfile(io.BytesIO(archive)):
        raise RuntimeError("旧版沙箱快照无效")
    _persist_snapshot(thread_id, archive)
    return archive


def _persist_snapshot(thread_id: str, archive: bytes) -> None:
    uri = put_snapshot(thread_id, archive)
    remember_snapshot(thread_id, uri=uri, sha256=hashlib.sha256(archive).hexdigest())


def _restore_snapshot(sandbox, archive: bytes, project_name: str | None) -> None:
    from opensandbox.models.filesystem import WriteEntry

    files = _checked_files(archive, project_name)
    folders = {"/projects"}
    for path, _ in files:
        parent = Path(path).parent
        while str(parent) not in {"/", "."}:
            folders.add(str(parent))
            parent = parent.parent
    ordered_folders = sorted(folders)
    for batch_start in range(0, len(ordered_folders), 100):
        batch = ordered_folders[batch_start:batch_start + 100]
        result = sandbox.commands.run(["mkdir", "-p", *batch])
        if result.exit_code != 0:
            raise RuntimeError("沙箱快照目录恢复失败")
    for start in range(0, len(files), 50):
        sandbox.files.write_files([
            WriteEntry(path=path, data=data, mode=644)
            for path, data in files[start:start + 50]
        ])


def _archive_from_sandbox(thread_id: str) -> tuple[str, bytes]:
    """Build a bounded ZIP inside the remote sandbox and transfer only its bytes."""
    from opensandbox.models.execd import RunCommandOpts
    from agent.core.graph import get_store

    thread = get_store().get_thread(thread_id)
    if not thread or not thread.get("sandbox_id"):
        raise ValueError("此会话没有可导出的沙箱项目")
    backend = ensure_sandbox_for_thread(thread_id)
    if thread_id in _workspace_notices:
        raise SandboxExpiredError("原沙箱没有可恢复的代码；当前新沙箱是空的，不能将其作为旧代码导出")
    sandbox = backend.sandbox
    archive_path = f"/tmp/ai-coding-{uuid.uuid4().hex}.zip"
    try:
        result = sandbox.commands.run(
            ["python3", "-c", _EXPORT_SCRIPT, "", archive_path, "/projects"],
            opts=RunCommandOpts(timeout=timedelta(seconds=60), working_directory="/projects"),
        )
        if result.exit_code != 0:
            logs = getattr(result, "logs", None)
            stderr = "".join(str(getattr(item, "text", "")) for item in getattr(logs, "stderr", []) or [])[:200].strip()
            raise RuntimeError(f"沙箱工作区导出失败：{stderr or '请检查 2000 文件 / 20 MiB 限额'}")
        info = sandbox.files.get_file_info([archive_path]).get(archive_path)
        if info is None or info.size > _MAX_BYTES:
            raise RuntimeError("导出压缩包超过 20 MiB 限额")
        return "workspace", sandbox.files.read_bytes(archive_path)
    finally:
        try:
            sandbox.files.delete_files([archive_path])
        except Exception:
            pass


def save_export_snapshot(thread_id: str) -> bool:
    """Persist nonempty code workspaces; return whether a snapshot was saved."""
    _, archive = _archive_from_sandbox(thread_id)
    if not _checked_files(archive, None):
        return False
    _persist_snapshot(thread_id, archive)
    return True


def export_project_zip(thread_id: str) -> tuple[str, bytes]:
    """Download the saved ZIP; older sessions fall back to a live sandbox."""
    from agent.core.graph import get_store

    thread = get_store().get_thread(thread_id)
    if not thread:
        raise ValueError("AI Coding 会话不存在")
    project = str(thread.get("sandbox_project") or "")
    archive = _load_snapshot(thread_id)
    if archive is not None:
        return project or "workspace", archive
    if not thread.get("sandbox_id"):
        raise ValueError("此会话没有可导出的沙箱项目")
    project, archive = _archive_from_sandbox(thread_id)
    if not _checked_files(archive, None):
        raise ValueError("沙箱工作区没有可导出的代码文件")
    _persist_snapshot(thread_id, archive)
    return project, archive


def delete_saved_export(thread_id: str) -> None:
    delete_snapshot(thread_id)
    forget_snapshot(thread_id)
    _legacy_saved_export_path(thread_id).unlink(missing_ok=True)
    _workspace_notices.pop(thread_id, None)


def close_sandbox_connections() -> None:
    """Release SDK connections on shutdown; sandbox lifetime is server-managed."""
    with _lock:
        for backend in _backends.values():
            backend.sandbox.close()
        _backends.clear()
