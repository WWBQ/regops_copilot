"""Gitee 相关 LangChain 工具。

本模块把 `gitee_api.py` 中的低层 API 调用包装成模型可调用的工具。
这里负责处理运行期上下文、只读任务拦截、任务事件记录和业务 Store 状态更新。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from agent.core.events import record_event
from agent.core.graph import get_store
from agent.tools.gitee_api import (
    create_pull_request,
    get_gitee_token,
    get_pull_request,
    list_pull_request_comments,
    list_pull_request_commits,
    list_pull_request_files,
    mask_token,
    parse_gitee_repo_url,
    post_pr_comment,
)
from agent.tools.runtime_context import get_runtime_thread_id, runtime_is_read_only_task

logger = logging.getLogger("agent.run.gitee")


@tool
def open_gitee_pull_request(
    owner: str,
    repo: str,
    head: str,
    base: str = "master",
    title: str = "金融风险审计助手 generated changes",
    body: str = "由金融风险审计助手的研发协作模式生成。",
) -> dict[str, Any]:
    """为已经推送到 Gitee 的分支创建或复用 Pull Request。

    Args:
        owner: Gitee 仓库 owner。
        repo: Gitee 仓库名称。
        head: 已推送的源分支。
        base: 目标分支，默认 master。
        title: PR 标题。
        body: PR 描述。

    Returns:
        成功时返回 `ok=True`、PR URL 和原始 API 数据；只读任务或 API 失败时返回错误信息。
    """

    if runtime_is_read_only_task():
        # 分析、规划、问答等只读任务不能执行外部写操作。
        # 这层拦截可以避免模型在用户尚未确认实施前创建 PR。
        return {
            "ok": False,
            "error": "当前任务是只读任务，不能创建 Pull Request。请先向用户输出方案或分析结论，等待确认实施。",
        }

    missing = _missing_gitee_token()
    if missing:
        return {"ok": False, "error": missing}
    thread_id = get_runtime_thread_id()
    # 记录关键参数但不记录 token；认证由 gitee_api 和 LocalShellBackend 内部处理。
    logger.info(
        "准备创建 Gitee PR：owner=%s repo=%s head=%s base=%s title=%s",
        owner,
        repo,
        head,
        base,
        title,
    )
    if thread_id:
        # 事件表用于前端展示工具执行进度，也便于排查 Agent 在哪个阶段失败。
        record_event(thread_id, "gitee:pr", "创建或复用 Pull Request", kind="fetch", status="in_progress")

    pr = create_pull_request(owner=owner, repo=repo, head=head, base=base, title=title, body=body)
    pr_url = pr.get("html_url") or pr.get("url") or ""

    if thread_id:
        # Store 中保存 PR 状态，后续任务列表、详情页和最终结果都可以直接读取。
        get_store().update_thread_status(thread_id, "pr_created", pr_url=pr_url, branch_name=head)
        record_event(
            thread_id,
            "gitee:pr",
            "创建或复用 Pull Request",
            kind="fetch",
            status="completed",
            detail=pr_url,
        )

    if pr.get("reused"):
        # 重复创建同一 head/base PR 时，底层 API 会返回 reused=True 的兼容结构。
        logger.info("Gitee PR 已存在，复用已有 PR：thread_id=%s pr_url=%s", thread_id, pr_url)
    else:
        logger.info("Gitee PR 创建完成：thread_id=%s pr_url=%s", thread_id, pr_url)
    return {"ok": True, "pr_url": pr_url, "raw": pr}


@tool
def publish_gitee_pr_comment(owner: str, repo: str, number: int, body: str) -> dict[str, Any]:
    """向指定 Gitee Pull Request 发布普通评论。

    Args:
        owner: Gitee 仓库 owner。
        repo: Gitee 仓库名称。
        number: PR 编号。
        body: 评论正文。

    Returns:
        Gitee API 返回的评论 JSON。
    """

    missing = _missing_gitee_token()
    if missing:
        return {"ok": False, "error": missing}
    # 评论内容可能较长，不写入日志；日志只保留仓库和 PR 编号用于问题定位。
    logger.info("准备发布 Gitee PR 评论：owner=%s repo=%s number=%s", owner, repo, number)
    return post_pr_comment(owner=owner, repo=repo, number=number, body=body)


@tool
def get_gitee_pull_request_context(owner: str, repo: str, number: int) -> dict[str, Any]:
    """读取 Gitee Pull Request 审查上下文。

    Reviewer 子 Agent 使用该工具获取 PR 标题、描述、变更文件、提交列表和已有评论。
    该工具只读，不会修改 Gitee 仓库。
    """

    logger.info("读取 Gitee PR 上下文：owner=%s repo=%s number=%s", owner, repo, number)
    pr = get_pull_request(owner=owner, repo=repo, number=number)
    commits = list_pull_request_commits(owner=owner, repo=repo, number=number)
    files = list_pull_request_files(owner=owner, repo=repo, number=number)
    comments = list_pull_request_comments(owner=owner, repo=repo, number=number)
    return {
        "pull_request": pr,
        "commits": commits,
        "files": files,
        "comments": comments,
        "summary": {
            "title": pr.get("title") if isinstance(pr, dict) else None,
            "state": pr.get("state") if isinstance(pr, dict) else None,
            "files_count": len(files),
            "commits_count": len(commits),
            "comments_count": len(comments),
        },
    }


def _missing_gitee_token() -> str | None:
    """密钥缺失时返回明确说明，不把异常伪装成成功。"""

    try:
        get_gitee_token()
    except RuntimeError as exc:
        return str(exc)
    return None


def _resolve_explicit_repo(repo_url: str):
    """只接受这句话里给出的仓库地址，空值不回落默认仓库。"""

    import re

    text = (repo_url or "").strip()
    if not text:
        return None, (
            "没有仓库地址。请在这句话里给出要上传到的 Gitee 仓库，"
            "不会使用默认仓库 https://gitee.com/msb-goldbin/ai_coding。"
        )
    if not text.startswith(("http://", "https://")):
        shorthand = text.removesuffix(".git").strip().strip("/")
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", shorthand):
            text = f"https://gitee.com/{shorthand}.git"
        else:
            return None, "仓库地址格式不正确。请给出 https://gitee.com/owner/repo 或 owner/repo。"
    try:
        return parse_gitee_repo_url(text), None
    except ValueError as exc:
        return None, str(exc)


@tool
def upload_to_gitee(repo_url: str, commit_message: str = "上传本地工作区改动") -> dict[str, Any]:
    """把当前会话本地工作区提交并推送到用户指定的 Gitee 仓库。

    只有用户明确说出上传、推上去、提交到仓库时才调用。
    repo_url 必须来自用户这句话，不能留空，不能使用默认仓库。
    缺少 GITEE_TOKEN 或 SCM_GITEE_TOKEN 时返回 ok=False，并写明缺什么。
    """

    from agent.backends.local_shell import get_local_shell_backend
    from agent.backends.permissions import ensure_safe_git_message

    repo, error = _resolve_explicit_repo(repo_url)
    if error or repo is None:
        return {"ok": False, "error": error or "没有仓库地址。"}
    missing = _missing_gitee_token()
    if missing:
        return {"ok": False, "error": missing}

    backend = get_local_shell_backend()
    cwd = "/projects"

    def run_git(command: str):
        result = backend.run(command, cwd=cwd, timeout=180)
        if result.exit_code != 0:
            detail = mask_token((result.stderr or result.stdout or "").strip())
            raise RuntimeError(f"{command} 失败：{detail or '没有输出'}")
        return result

    try:
        probe = backend.run("git rev-parse --is-inside-work-tree", cwd=cwd, timeout=30)
        if probe.exit_code != 0:
            run_git("git init -b master")
        remote = backend.run("git remote get-url origin", cwd=cwd, timeout=30)
        if remote.exit_code != 0:
            run_git(f"git remote add origin {repo.clone_url}")
        else:
            run_git(f"git remote set-url origin {repo.clone_url}")
        status = backend.run("git status --porcelain", cwd=cwd, timeout=30)
        if status.exit_code != 0:
            detail = mask_token((status.stderr or status.stdout or "").strip())
            return {"ok": False, "error": f"无法读取本地工作区状态：{detail or '没有输出'}"}
        if status.stdout.strip():
            run_git("git add -A")
            message = ensure_safe_git_message(commit_message)
            run_git(
                "git -c user.name=Financial-Risk-Audit-Assistant -c user.email=financial-risk-audit@local "
                f'commit -m "{message}"'
            )
        pushed = run_git("git push -u origin HEAD")
    except Exception as exc:
        logger.exception("上传本地工作区到 Gitee 失败")
        return {"ok": False, "error": mask_token(str(exc))}

    logger.info("本地工作区已上传：repo=%s/%s", repo.owner, repo.repo)
    return {
        "ok": True,
        "repo": f"{repo.owner}/{repo.repo}",
        "clone_url": repo.clone_url,
        "detail": mask_token((pushed.stdout or pushed.stderr or "").strip()),
    }
