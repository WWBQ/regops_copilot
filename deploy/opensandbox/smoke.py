"""One-shot local OpenSandbox smoke test; always destroys the test sandbox."""

from datetime import timedelta

from opensandbox import SandboxSync
from opensandbox.models.filesystem import WriteEntry
from opensandbox.models.sandboxes import NetworkPolicy

from agent.backends.open_sandbox import _connection_config
from agent.env_utils import get_env


def _stdout(result) -> str:
    return "".join(item.text for item in result.logs.stdout).strip()


def main() -> None:
    sandbox = None
    try:
        sandbox = SandboxSync.create(
            image=get_env("AI_CODING_SANDBOX_IMAGE", "opensandbox/code-interpreter:v1.1.0"),
            timeout=timedelta(minutes=5),
            resource={"cpu": "1", "memory": "1Gi"},
            network_policy=NetworkPolicy(defaultAction="deny", egress=[]),
            connection_config=_connection_config(),
        )
        result = sandbox.commands.run(["python3", "-c", "print(6 * 7)"])
        assert result.exit_code == 0 and _stdout(result) == "42", "命令执行失败"

        path = "/tmp/opensandbox-smoke.txt"
        sandbox.files.write_files([WriteEntry(path=path, data=b"isolated\n", mode=600)])
        assert sandbox.files.read_bytes(path) == b"isolated\n", "文件读写失败"

        probes = [
            ("DNS", "import socket; socket.gethostbyname('example.com')"),
            ("public IP", "import socket; socket.create_connection(('1.1.1.1', 443), timeout=4)"),
        ]
        for label, program in probes:
            blocked = sandbox.commands.run(["python3", "-c", program])
            assert blocked.exit_code != 0, f"{label} 出网未被阻断"
        print("PASS: 命令、文件、DNS 拒绝、公网 IP 拒绝")
    finally:
        if sandbox is not None:
            sandbox.destroy()
            sandbox.close()


if __name__ == "__main__":
    main()
