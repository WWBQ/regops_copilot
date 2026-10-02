"""金融审计模式的本地文件/命令硬边界。"""

from __future__ import annotations

from deepagents.backends.protocol import EditResult, ExecuteResponse, FileUploadResponse, WriteResult

from agent.backends.local_shell import CommandResult, LocalShellBackend


_DENIED = "金融风险审计模式为只读任务，不允许执行命令或修改工作区。"


class FinancialReadOnlyBackend(LocalShellBackend):
    """即使模型越过提示词或文件权限，也不执行本机写操作。"""

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return ExecuteResponse(output=_DENIED, exit_code=126, truncated=False)

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_DENIED)

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        return EditResult(error=_DENIED)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error=_DENIED) for path, _ in files]

    def write_file(self, path: str, content: str) -> str:
        raise PermissionError(_DENIED)

    def run(self, command: str, cwd: str = ".", timeout: int = 300) -> CommandResult:
        return CommandResult(command=command, cwd=cwd, exit_code=126, stdout="", stderr=_DENIED)
