"""可版本化 Prompt 资产：System/User 分界、变量注入、钉扎、变更记录、回滚。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PROMPTS_DIR / "templates"
PINS_FILE = PROMPTS_DIR / "pins.json"

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_VAR_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_TEMPLATE_NAME_RE = re.compile(r"^[a-z][a-z0-9_.]{1,64}$")


class PromptLibraryError(ValueError):
    """模板不存在、缺变量、缺评测绑定或版本不合法。"""


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    version: str
    role: str
    scene: str
    system: str
    user: str | None
    variables: tuple[str, ...]

    def messages(self, *, extra_user: str | None = None) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        if self.system:
            rows.append({"role": "system", "content": self.system})
        user = extra_user if extra_user is not None else self.user
        if user:
            rows.append({"role": "user", "content": user})
        return rows


@dataclass(frozen=True)
class PromptRecord:
    name: str
    role: str
    scene: str
    variables: tuple[str, ...]
    changelog: tuple[dict[str, Any], ...]
    versions: dict[str, dict[str, str]]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _validate_changelog_entry(entry: dict[str, Any], *, name: str) -> None:
    version = str(entry.get("version") or "")
    if not _VERSION_RE.match(version):
        raise PromptLibraryError(f"{name}: changelog 版本号须为 x.y.z")
    if not str(entry.get("reason") or "").strip():
        raise PromptLibraryError(f"{name}@{version}: 变更必须写 reason")
    eval_task = str(entry.get("eval_task") or "").strip()
    eval_report = str(entry.get("eval_report") or "").strip()
    if not eval_task and not eval_report:
        raise PromptLibraryError(f"{name}@{version}: 改模板必须绑定 eval_task 或 eval_report")


def _load_record(name: str, *, templates_dir: Path) -> PromptRecord:
    if not _TEMPLATE_NAME_RE.match(name):
        raise PromptLibraryError(f"非法模板名: {name}")
    path = templates_dir / f"{name}.json"
    if not path.is_file():
        raise PromptLibraryError(f"未知 Prompt 模板: {name}")
    raw = _read_json(path)
    if str(raw.get("id") or "") != name:
        raise PromptLibraryError(f"{path.name}: id 必须等于文件名")
    changelog = tuple(raw.get("changelog") or ())
    if not changelog:
        raise PromptLibraryError(f"{name}: 缺少 changelog")
    for entry in changelog:
        if not isinstance(entry, dict):
            raise PromptLibraryError(f"{name}: changelog 项必须是对象")
        _validate_changelog_entry(entry, name=name)
    versions_raw = raw.get("versions") or {}
    if not isinstance(versions_raw, dict) or not versions_raw:
        raise PromptLibraryError(f"{name}: 缺少 versions")
    versions: dict[str, dict[str, str]] = {}
    for version, body in versions_raw.items():
        if not _VERSION_RE.match(str(version)):
            raise PromptLibraryError(f"{name}: 非法版本 {version}")
        if not isinstance(body, dict):
            raise PromptLibraryError(f"{name}@{version}: 正文必须是对象")
        system = str(body.get("system") or "")
        user = body.get("user")
        if not system.strip():
            raise PromptLibraryError(f"{name}@{version}: system 不能为空")
        versions[str(version)] = {
            "system": system,
            "user": "" if user is None else str(user),
        }
    changelog_versions = {str(entry["version"]) for entry in changelog}
    missing_log = set(versions) - changelog_versions
    if missing_log:
        raise PromptLibraryError(f"{name}: 版本 {sorted(missing_log)} 缺少 changelog")
    variables = tuple(str(item) for item in (raw.get("variables") or []))
    return PromptRecord(
        name=name,
        role=str(raw.get("role") or "system"),
        scene=str(raw.get("scene") or ""),
        variables=variables,
        changelog=changelog,  # type: ignore[arg-type]
        versions=versions,
    )


def load_pins(*, pins_file: Path = PINS_FILE) -> dict[str, str]:
    if not pins_file.is_file():
        return {}
    raw = _read_json(pins_file)
    return {str(key): str(value) for key, value in raw.items()}


def list_template_names(*, templates_dir: Path = TEMPLATES_DIR) -> list[str]:
    names = [path.stem for path in sorted(templates_dir.glob("*.json"))]
    return names


def get_record(name: str, *, templates_dir: Path = TEMPLATES_DIR) -> PromptRecord:
    return _load_record(name, templates_dir=templates_dir)


def active_version(
    name: str,
    *,
    pins_file: Path = PINS_FILE,
    templates_dir: Path = TEMPLATES_DIR,
) -> str:
    record = get_record(name, templates_dir=templates_dir)
    pins = load_pins(pins_file=pins_file)
    pinned = pins.get(name)
    if pinned:
        if pinned not in record.versions:
            raise PromptLibraryError(f"{name}: 钉扎版本 {pinned} 不存在")
        return pinned
    return next(str(entry["version"]) for entry in reversed(record.changelog))


def list_versions(name: str, *, templates_dir: Path = TEMPLATES_DIR) -> list[dict[str, Any]]:
    record = get_record(name, templates_dir=templates_dir)
    rows: list[dict[str, Any]] = []
    for entry in record.changelog:
        version = str(entry["version"])
        body = record.versions.get(version, {})
        rows.append(
            {
                "version": version,
                "date": entry.get("date"),
                "reason": entry.get("reason"),
                "eval_task": entry.get("eval_task"),
                "eval_report": entry.get("eval_report"),
                "status": entry.get("status") or "active",
                "has_user": bool(body.get("user")),
            }
        )
    return rows


def list_templates(
    *,
    pins_file: Path = PINS_FILE,
    templates_dir: Path = TEMPLATES_DIR,
) -> list[dict[str, Any]]:
    pins = load_pins(pins_file=pins_file)
    rows: list[dict[str, Any]] = []
    for name in list_template_names(templates_dir=templates_dir):
        record = get_record(name, templates_dir=templates_dir)
        current = pins.get(name) or active_version(
            name, pins_file=pins_file, templates_dir=templates_dir
        )
        rows.append(
            {
                "id": name,
                "role": record.role,
                "scene": record.scene,
                "variables": list(record.variables),
                "current_version": current,
                "versions": [str(entry["version"]) for entry in record.changelog],
            }
        )
    return rows


def _substitute(text: str, *, allowed: tuple[str, ...], values: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in allowed:
            return match.group(0)
        if key not in values:
            raise PromptLibraryError(f"缺少变量 {{{key}}}")
        return str(values[key])

    return _VAR_RE.sub(repl, text)


def render(
    name: str,
    *,
    version: str | None = None,
    pins_file: Path = PINS_FILE,
    templates_dir: Path = TEMPLATES_DIR,
    **variables: Any,
) -> RenderedPrompt:
    record = get_record(name, templates_dir=templates_dir)
    resolved = version or active_version(
        name, pins_file=pins_file, templates_dir=templates_dir
    )
    body = record.versions.get(resolved)
    if body is None:
        raise PromptLibraryError(f"{name}: 版本 {resolved} 不存在")
    missing_allowed = [key for key in variables if key not in record.variables]
    if missing_allowed:
        raise PromptLibraryError(f"{name}: 未声明的变量 {missing_allowed}")
    system = _substitute(body["system"], allowed=record.variables, values=variables)
    user_raw = body.get("user") or ""
    user = (
        _substitute(user_raw, allowed=record.variables, values=variables) if user_raw else None
    )
    return RenderedPrompt(
        name=name,
        version=resolved,
        role=record.role,
        scene=record.scene,
        system=system,
        user=user,
        variables=record.variables,
    )


def render_system(name: str, *, version: str | None = None, **variables: Any) -> str:
    return render(name, version=version, **variables).system


def pin(
    name: str,
    version: str,
    *,
    pins_file: Path = PINS_FILE,
    templates_dir: Path = TEMPLATES_DIR,
) -> dict[str, str]:
    record = get_record(name, templates_dir=templates_dir)
    if version not in record.versions:
        raise PromptLibraryError(f"{name}: 无法钉扎不存在的版本 {version}")
    pins = load_pins(pins_file=pins_file)
    pins[name] = version
    _write_json(pins_file, pins)
    return pins


def rollback(
    name: str,
    version: str,
    *,
    pins_file: Path = PINS_FILE,
    templates_dir: Path = TEMPLATES_DIR,
) -> dict[str, str]:
    """把钉扎改回已有版本。不删模板正文，只改 pins.json。"""
    return pin(name, version, pins_file=pins_file, templates_dir=templates_dir)


def changelog(name: str, *, templates_dir: Path = TEMPLATES_DIR) -> list[dict[str, Any]]:
    return list_versions(name, templates_dir=templates_dir)
