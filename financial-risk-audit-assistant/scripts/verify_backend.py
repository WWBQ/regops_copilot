from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.app import app
from agent.env_utils import get_env
from agent.backends.permissions import ensure_safe_command
from agent.core.graph import build_agent
from agent.tools.gitee_api import parse_gitee_repo_url


def assert_status(name: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected HTTP {expected}, got {actual}")


def main() -> None:
    # 这个脚本只做后端基础自检，不会调用真实模型，也不会向 Gitee push。
    # 真实端到端验收请使用 scripts\verify_gitee_e2e.py 并传入测试仓库地址。
    client = TestClient(app)

    assert_status("health", client.get("/health").status_code, 200)
    auth_headers = {
        "X-Regops-Service-Token": get_env("REGOPS_SERVICE_TOKEN"),
        "X-Regops-User": "00000000-0000-0000-0000-000000000001",
    }
    assert_status("dashboard unauthorized", client.get("/regops/agent/threads").status_code, 401)
    for path in [
        "/regops/agent/options",
        "/regops/agent/threads",
    ]:
        assert_status(path, client.get(path, headers=auth_headers).status_code, 200)
    other_id = "00000000-0000-0000-0000-000000000002_00000000-0000-0000-0000-000000000003"
    assert_status(
        "cross-user thread hidden",
        client.get(f"/regops/agent/threads/{other_id}", headers=auth_headers).status_code,
        404,
    )

    repo = parse_gitee_repo_url("https://gitee.com/owner/repo.git")
    assert repo.owner == "owner"
    assert repo.repo == "repo"

    for command in ["python --version", "git status --short", "pytest --version", "pip install -r requirements.txt 2>&1"]:
        ensure_safe_command(command)
    for command in ["echo ok", "python --version && dir", "rm -rf .", "del /q file.txt"]:
        try:
            ensure_safe_command(command)
        except Exception:
            pass
        else:
            raise AssertionError(f"dangerous command was allowed: {command}")

    agent = build_agent("verify-backend")
    assert type(agent).__name__ == "CompiledStateGraph"
    print("backend verification passed")


if __name__ == "__main__":
    main()
