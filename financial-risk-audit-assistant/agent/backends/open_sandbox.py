"""OpenSandbox-backed DeepAgents execution for AI Coding only.

Host files are copied into an isolated sandbox once per thread. No host directory,
API key or Git credential is mounted inside the container.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox

from agent.core.settings import PROJECTS_DIR, SKILLS_DIR
from agent.env_utils import get_env

_lock = threading.RLock()
_backends: dict[str, OpenSandboxBackend] = {}
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".secrets", "dist", "build"}
_SKIP_FILES = {
    ".env", ".env.local", ".env.production", ".npmrc", ".pypirc",
    ".git-credentials", "credentials.json", "id_rsa", "id_ed25519",
}
_SKIP_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"}
_MAX_FILES = 2000
_MAX_BYTES = 20 * 1024 * 1024


def execution_backend() -> str:
    mode = get_env("AI_CODING_EXECUTION_BACKEND", "local").strip().lower()
    if mode not in {"local", "opensandbox"}:
        raise ValueError("AI_CODING_EXECUTION_BACKEND 只能是 local 或 opensandbox")
    return mode


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


def _seed(sandbox, project_name: str | None) -> None:
    from opensandbox.models.filesystem import WriteEntry

    snapshots: list[tuple[str, bytes]] = []
    if project_name:
        project_root = PROJECTS_DIR / project_name
        if project_root.parent.resolve() != PROJECTS_DIR.resolve() or project_root.name != project_name:
            raise ValueError("项目名称无效")
        snapshots.extend(_snapshot(project_root, f"/projects/{project_name}"))
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


def ensure_sandbox_for_thread(thread_id: str) -> OpenSandboxBackend:
    from opensandbox import SandboxSync
    from opensandbox.models.sandboxes import NetworkPolicy
    from agent.core.graph import get_store

    with _lock:
        if thread_id in _backends:
            backend = _backends[thread_id]
            try:
                backend.sandbox.renew(timedelta(minutes=60))
            except Exception as exc:
                _backends.pop(thread_id, None)
                raise RuntimeError("原 OpenSandbox 续期失败；未回退本机执行") from exc
            return backend
        store = get_store()
        thread = store.get_thread(thread_id)
        if thread is None:
            raise RuntimeError("AI Coding 会话不存在")
        config = _connection_config()
        sandbox_id = thread.get("sandbox_id")
        if sandbox_id:
            try:
                sandbox = SandboxSync.connect(str(sandbox_id), connection_config=config)
                sandbox.renew(timedelta(minutes=60))
            except Exception as exc:
                raise RuntimeError("原 OpenSandbox 不可用或已过期；不会新建空沙箱或回退本机") from exc
        else:
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
                _seed(sandbox, thread.get("sandbox_project"))
                store.set_thread_sandbox(thread_id, sandbox_id=str(sandbox.id))
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
root = pathlib.Path(sys.argv[3]) / project
if not root.is_dir() or root.is_symlink():
    raise SystemExit('project missing')
count = 0
total = 0
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', 'venv', 'dist', 'build'} and not (pathlib.Path(current) / d).is_symlink()]
        for name in names:
            path = pathlib.Path(current) / name
            if path.is_symlink() or not path.is_file() or (name.startswith('.') and name not in {'.gitignore', '.editorconfig'}) or path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx'}:
                continue
            count += 1
            total += path.stat().st_size
            if count > 2000 or total > 20 * 1024 * 1024:
                raise SystemExit('export exceeds size or file limit')
            archive.write(path, arcname=f'{project}/{path.relative_to(root).as_posix()}')
"""


def export_project_zip(thread_id: str) -> tuple[str, bytes]:
    """Export a bounded archive from the remote sandbox; never write host files."""
    from opensandbox.models.execd import RunCommandOpts
    from agent.core.graph import get_store

    thread = get_store().get_thread(thread_id)
    if not thread or not thread.get("sandbox_id") or not thread.get("sandbox_project"):
        raise ValueError("此会话没有可导出的沙箱项目")
    project = str(thread["sandbox_project"])
    if Path(project).name != project or project in {".", ".."} or "\\" in project:
        raise ValueError("沙箱项目名称无效")
    backend = ensure_sandbox_for_thread(thread_id)
    sandbox = backend.sandbox
    archive_path = f"/tmp/ai-coding-{uuid.uuid4().hex}.zip"
    try:
        result = sandbox.commands.run(
            ["python3", "-c", _EXPORT_SCRIPT, project, archive_path, "/projects"],
            opts=RunCommandOpts(timeout=timedelta(seconds=60), working_directory="/projects"),
        )
        if result.exit_code != 0:
            raise RuntimeError("沙箱项目导出失败或超过 2000 文件 / 20 MiB 限额")
        info = sandbox.files.get_file_info([archive_path]).get(archive_path)
        if info is None or info.size > _MAX_BYTES:
            raise RuntimeError("导出压缩包超过 20 MiB 限额")
        return project, sandbox.files.read_bytes(archive_path)
    finally:
        try:
            sandbox.files.delete_files([archive_path])
        except Exception:
            pass


def close_sandbox_connections() -> None:
    """Release SDK connections on shutdown; sandbox lifetime is server-managed."""
    with _lock:
        for backend in _backends.values():
            backend.sandbox.close()
        _backends.clear()
