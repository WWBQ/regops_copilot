"""Safely import user-owned code files into an AI Coding sandbox."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from pathlib import PurePosixPath

from agent.backends.open_sandbox import (
    _MAX_BYTES,
    _MAX_FILES,
    _SKIP_DIRS,
    _SKIP_FILES,
    _SKIP_SUFFIXES,
    consume_workspace_notice,
    ensure_sandbox_for_thread,
    save_export_snapshot,
)


class UploadRejected(ValueError):
    """Invalid upload or a conflict with existing sandbox files."""


def _safe_relative_path(name: str) -> str:
    if not name or len(name) > 512 or "\\" in name or "\x00" in name or name.startswith("/"):
        raise UploadRejected("文件路径无效")
    parts = name.split("/")
    if len(parts) > 32 or any(part in {"", ".", ".."} for part in parts):
        raise UploadRejected("压缩包包含不安全的文件路径")
    for part in parts:
        if (part in _SKIP_DIRS or part in _SKIP_FILES
                or (part.startswith(".") and part not in {".gitignore", ".editorconfig"})
                or PurePosixPath(part).suffix.lower() in _SKIP_SUFFIXES):
            raise UploadRejected("上传内容包含隐藏目录或凭据文件；请先移除")
    return "/".join(parts)


def prepare_upload(filename: str, body: bytes) -> list[tuple[str, bytes]]:
    if not body or len(body) > _MAX_BYTES:
        raise UploadRejected("单次上传不得为空或超过 20 MiB")
    if not filename or "/" in filename or "\\" in filename:
        raise UploadRejected("上传文件名必须是不含路径的文件名")
    _safe_relative_path(filename)
    if not filename.lower().endswith(".zip"):
        return [(f"/projects/{filename}", body)]
    if not zipfile.is_zipfile(io.BytesIO(body)):
        raise UploadRejected("ZIP 压缩包无效")
    files: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if len(archive.infolist()) > _MAX_FILES + 100:
            raise UploadRejected("压缩包文件数量超过上限")
        for item in archive.infolist():
            path = item.filename.removesuffix("/") if item.is_dir() else item.filename
            relative = _safe_relative_path(path)
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if item.flag_bits & 1 or (kind not in {0, stat.S_IFREG, stat.S_IFDIR}) or stat.S_ISLNK(mode):
                raise UploadRejected("压缩包包含符号链接、特殊文件或加密文件")
            if item.is_dir():
                continue
            if relative in seen:
                raise UploadRejected("压缩包包含重名文件")
            seen.add(relative)
            total += item.file_size
            if len(seen) > _MAX_FILES or total > _MAX_BYTES:
                raise UploadRejected("压缩包解压后超过 2000 文件或 20 MiB")
            try:
                content = archive.read(item)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise UploadRejected("压缩包校验失败") from exc
            files.append((f"/projects/{relative}", content))
    if not files:
        raise UploadRejected("压缩包中没有可导入的文件")
    for relative in seen:
        for parent in PurePosixPath(relative).parents:
            if str(parent) in seen:
                raise UploadRejected("压缩包中有文件与目录重名")
    return files


_PREFLIGHT = r"""
import json, os, pathlib, sys
root = pathlib.Path('/projects')
targets = json.loads(sys.argv[1])
new_bytes = int(sys.argv[2])
if not root.is_dir() or root.is_symlink():
    raise SystemExit('sandbox workspace unavailable')
existing_files = 0
existing_bytes = 0
for current, dirs, names in os.walk(root, followlinks=False):
    dirs[:] = [d for d in dirs if not (pathlib.Path(current) / d).is_symlink()]
    for name in names:
        path = pathlib.Path(current) / name
        if path.is_file() and not path.is_symlink():
            existing_files += 1
            existing_bytes += path.stat().st_size
if existing_files + len(targets) > 2000 or existing_bytes + new_bytes > 20 * 1024 * 1024:
    raise SystemExit('workspace exceeds 2000 files or 20 MiB')
for target in targets:
    path = pathlib.Path(target)
    if root not in path.parents or path.exists() or path.is_symlink():
        raise SystemExit('target already exists or is outside workspace')
    current = path.parent
    while current != root:
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise SystemExit('target parent is not a safe directory')
        current = current.parent
print('UPLOAD_OK')
"""


def upload_to_workspace(thread_id: str, filename: str, body: bytes) -> dict[str, object]:
    """Validate all input before creating the sandbox; never overwrite files."""
    from opensandbox.models.filesystem import WriteEntry

    files = prepare_upload(filename, body)
    backend = ensure_sandbox_for_thread(thread_id)
    sandbox = backend.sandbox
    paths = [path for path, _ in files]
    result = sandbox.commands.run([
        "python3", "-c", _PREFLIGHT, json.dumps(paths), str(sum(len(data) for _, data in files)),
    ])
    if result.exit_code != 0:
        raise UploadRejected("目标文件已存在、路径不安全，或工作区超过 2000 文件 / 20 MiB")
    folders = {str(PurePosixPath(path).parent) for path in paths}
    for parent in tuple(folders):
        while parent not in {"/", "/projects"}:
            parent = str(PurePosixPath(parent).parent)
            folders.add(parent)
    for start in range(0, len(folders), 100):
        batch = sorted(folders)[start:start + 100]
        made = sandbox.commands.run(["mkdir", "-p", *batch])
        if made.exit_code != 0:
            raise RuntimeError("沙箱目录创建失败")
    for start in range(0, len(files), 50):
        sandbox.files.write_files([
            WriteEntry(path=path, data=data, mode=644) for path, data in files[start:start + 50]
        ])
    notice = consume_workspace_notice(thread_id)
    try:
        snapshot_saved = save_export_snapshot(thread_id)
    except Exception:
        return {
            "file_count": len(files), "snapshot_saved": False,
            "message": "文件已进入沙箱，但对象存储快照保存失败；请在沙箱过期前重试导出。",
            "workspace_notice": notice,
        }
    return {
        "file_count": len(files), "snapshot_saved": snapshot_saved,
        "message": f"已导入 {len(files)} 个文件" + ("并保存代码快照。" if snapshot_saved else "，但没有可导出的代码文件。"),
        "workspace_notice": notice,
    }
