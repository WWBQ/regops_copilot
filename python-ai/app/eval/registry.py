"""评测任务注册表（eval/tasks.json 可增删）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = PROJECT_ROOT / "eval"
GOLDEN_DIR = EVAL_DIR / "golden"
REPORTS_DIR = EVAL_DIR / "reports"
TASKS_FILE = EVAL_DIR / "tasks.json"

RUNNERS = ("w1_chat", "rag_retrieval", "compliance_schema", "w4_asknum", "w6_number_check", "w6_workflow")
RUNNER_DEFAULT_METRICS: dict[str, tuple[str, ...]] = {
    "w1_chat": ("accuracy", "refuse_rate", "latency_p50_ms"),
    "rag_retrieval": ("recall_at_k", "mrr"),
    "compliance_schema": ("accuracy", "false_accept_rate", "false_reject_rate"),
    "w4_asknum": ("accuracy", "route_accuracy", "leak_rate"),
    "w6_number_check": ("accuracy", "false_accept_rate", "number_error_rate", "unit_error_rate"),
    "w6_workflow": ("accuracy", "param_accuracy", "avg_steps", "confirmation_rate"),
}
_TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


@dataclass(frozen=True)
class EvalTask:
    id: str
    name: str
    description: str
    golden_file: str
    runner: str
    metrics: tuple[str, ...]
    builtin: bool = False

    @property
    def golden_path(self) -> Path:
        return GOLDEN_DIR / self.golden_file


def _default_tasks_payload() -> dict:
    return {
        "version": "eval-tasks-v1",
        "tasks": [
            {
                "id": "w1_chat",
                "name": "W1 聊天评测",
                "description": "30 题闭卷金融能力：监管制度 + 会计/银行/市场概念（/chat，use_rag=false）",
                "golden_file": "w1_chat_30.json",
                "runner": "w1_chat",
                "metrics": list(RUNNER_DEFAULT_METRICS["w1_chat"]),
                "builtin": True,
            },
            {
                "id": "rag_retrieval",
                "name": "RAG 检索评测",
                "description": "100 题：Hybrid 检索 page 粒度 Recall@k / MRR",
                "golden_file": "rag_retrieval_100.json",
                "runner": "rag_retrieval",
                "metrics": list(RUNNER_DEFAULT_METRICS["rag_retrieval"]),
                "builtin": True,
            },
            {
                "id": "compliance_schema",
                "name": "合规结论 Schema 校验",
                "description": "20 例：10 合法 + 10 非法，统计误放行/误拒与报错理由命中率",
                "golden_file": "compliance_schema_20.json",
                "runner": "compliance_schema",
                "metrics": list(RUNNER_DEFAULT_METRICS["compliance_schema"]),
                "builtin": True,
            },
            {
                "id": "w4_asknum",
                "name": "W4 问数评测",
                "description": "20 题：命中 / 拦截 / 反问 / 跳过，检查路由与数字泄露（不调 LLM）",
                "golden_file": "w4_asknum_20.json",
                "runner": "w4_asknum",
                "metrics": list(RUNNER_DEFAULT_METRICS["w4_asknum"]),
                "builtin": True,
            },
            {
                "id": "w6_number_check",
                "name": "W6 数字校验",
                "description": "20 例：抽取终稿数字并回溯事实/引用，统计误放行与量纲错误（不调 LLM）",
                "golden_file": "w6_number_check_20.json",
                "runner": "w6_number_check",
                "metrics": list(RUNNER_DEFAULT_METRICS["w6_number_check"]),
                "builtin": True,
            },
            {
                "id": "w6_workflow",
                "name": "W6 工作流轨迹",
                "description": "20 场景：节点顺序、工具参数、确认率和失败节点（不调 LLM）",
                "golden_file": "w6_workflow_20.json",
                "runner": "w6_workflow",
                "metrics": list(RUNNER_DEFAULT_METRICS["w6_workflow"]),
                "builtin": True,
            },
        ],
    }


def _ensure_tasks_file() -> None:
    if TASKS_FILE.is_file():
        return
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(
        json.dumps(_default_tasks_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_task(raw: dict) -> EvalTask:
    runner = str(raw["runner"])
    if runner not in RUNNERS:
        raise ValueError(f"unsupported runner: {runner}")
    metrics_raw = raw.get("metrics") or list(RUNNER_DEFAULT_METRICS[runner])
    return EvalTask(
        id=str(raw["id"]),
        name=str(raw["name"]),
        description=str(raw.get("description") or ""),
        golden_file=str(raw["golden_file"]),
        runner=runner,
        metrics=tuple(str(m) for m in metrics_raw),
        builtin=bool(raw.get("builtin", False)),
    )


def _load_raw_tasks() -> list[dict]:
    _ensure_tasks_file()
    payload = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    return list(payload.get("tasks") or [])


def _save_raw_tasks(tasks: list[dict]) -> None:
    payload = {"version": "eval-tasks-v1", "tasks": tasks}
    TASKS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_all_tasks() -> dict[str, EvalTask]:
    tasks: dict[str, EvalTask] = {}
    for raw in _load_raw_tasks():
        task = _parse_task(raw)
        tasks[task.id] = task
    return tasks


def get_task(task_id: str) -> EvalTask:
    tasks = load_all_tasks()
    task = tasks.get(task_id)
    if task is None:
        raise KeyError(f"unknown eval task: {task_id}")
    return task


def list_golden_files() -> list[dict]:
    if not GOLDEN_DIR.is_dir():
        return []
    rows: list[dict] = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        item_count = 0
        version = None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            item_count = len(payload.get("items") or [])
            version = payload.get("version")
        except Exception:
            pass
        rows.append(
            {
                "filename": path.name,
                "item_count": item_count,
                "version": version,
            }
        )
    return rows


def preview_golden_set(filename: str) -> dict:
    _validate_golden_file(filename)
    path = GOLDEN_DIR / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict] = []
    for raw in payload.get("items") or []:
        if not isinstance(raw, dict):
            continue
        question = str(raw.get("question") or raw.get("rule") or "").strip()
        items.append(
            {
                "id": str(raw.get("id") or ""),
                "category": raw.get("category"),
                "question": question[:240],
            }
        )
    categories = sorted({str(item["category"]) for item in items if item.get("category")})
    return {
        "filename": filename,
        "version": payload.get("version"),
        "item_count": len(items),
        "categories": categories,
        "items": items,
    }


def _validate_golden_file(filename: str) -> None:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ValueError("invalid golden_file")
    path = GOLDEN_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"golden set not found: {filename}")


def _validate_task_id(task_id: str) -> None:
    if not _TASK_ID_RE.match(task_id):
        raise ValueError("task id 须为小写字母/数字/下划线，且以字母开头")


def task_to_dict(task: EvalTask) -> dict:
    golden_path = task.golden_path
    item_count = 0
    golden_version = None
    if golden_path.is_file():
        payload = json.loads(golden_path.read_text(encoding="utf-8"))
        item_count = len(payload.get("items") or [])
        golden_version = payload.get("version")
    return {
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "golden_file": task.golden_file,
        "golden_version": golden_version,
        "item_count": item_count,
        "metrics": list(task.metrics),
        "runner": task.runner,
        "builtin": task.builtin,
    }


def create_task(
    *,
    task_id: str,
    name: str,
    description: str,
    golden_file: str,
    runner: str,
    metrics: list[str] | None = None,
) -> EvalTask:
    _validate_task_id(task_id)
    tasks = load_all_tasks()
    if task_id in tasks:
        raise ValueError(f"task already exists: {task_id}")
    if runner not in RUNNERS:
        raise ValueError(f"unsupported runner: {runner}")
    _validate_golden_file(golden_file)

    resolved_metrics = tuple(metrics or RUNNER_DEFAULT_METRICS[runner])
    task = EvalTask(
        id=task_id,
        name=name.strip(),
        description=description.strip(),
        golden_file=golden_file,
        runner=runner,
        metrics=resolved_metrics,
        builtin=False,
    )
    raw_tasks = _load_raw_tasks()
    raw_tasks.append(
        {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "golden_file": task.golden_file,
            "runner": task.runner,
            "metrics": list(task.metrics),
            "builtin": False,
        }
    )
    _save_raw_tasks(raw_tasks)
    return task


def delete_task(task_id: str) -> None:
    tasks = load_all_tasks()
    task = tasks.get(task_id)
    if task is None:
        raise KeyError(f"unknown eval task: {task_id}")
    if task.builtin:
        raise ValueError("内置任务不可删除")

    raw_tasks = [raw for raw in _load_raw_tasks() if raw.get("id") != task_id]
    _save_raw_tasks(raw_tasks)


_GOLDEN_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,80}\.json$")


def validate_golden_payload(content: dict, *, runner: str | None = None) -> int:
    if not isinstance(content, dict):
        raise ValueError("黄金集必须是 JSON 对象")
    items = content.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("黄金集 items 必须为非空数组")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] 必须是对象")
        if runner == "compliance_schema":
            # Schema 校验集没有 question，改为要求 payload + category
            if not isinstance(item.get("payload"), dict):
                raise ValueError(f"items[{index}] 缺少 payload 对象（Schema 校验集必填）")
            if item.get("category") not in {"valid", "invalid"}:
                raise ValueError(f"items[{index}] category 须为 valid 或 invalid")
            continue
        if not str(item.get("question") or "").strip():
            raise ValueError(f"items[{index}] 缺少 question")
        if runner == "rag_retrieval":
            if not item.get("doc_id"):
                raise ValueError(f"items[{index}] 缺少 doc_id（RAG 检索集必填）")
            gold_pages = item.get("gold_pages")
            if not isinstance(gold_pages, list) or not gold_pages:
                raise ValueError(f"items[{index}] 缺少 gold_pages（RAG 检索集必填）")
        if runner == "w4_asknum":
            if item.get("expected_route") not in {
                "metric",
                "metric_blocked",
                "metric_clarify",
                "skip",
            }:
                raise ValueError(
                    f"items[{index}] expected_route 须为 metric / metric_blocked / metric_clarify / skip"
                )
        if runner == "w6_number_check":
            if not str(item.get("reply") or "").strip():
                raise ValueError(f"items[{index}] 缺少 reply（数字校验集必填）")
            if not isinstance(item.get("expected_ok"), bool):
                raise ValueError(f"items[{index}] expected_ok 须为布尔值")
        if runner == "w6_workflow":
            if item.get("expected_entry") not in {None, "graph", "asknum", "tools"}:
                raise ValueError(f"items[{index}] expected_entry 须为 graph / asknum / tools")
    return len(items)


def save_golden_set(*, filename: str, content: dict, runner: str | None = None) -> dict:
    name = filename.strip()
    if not _GOLDEN_FILENAME_RE.match(name):
        raise ValueError("文件名须为 .json，仅含字母数字、点、下划线、连字符")
    if name in {
        "w1_chat_30.json",
        "rag_retrieval_100.json",
        "compliance_schema_20.json",
        "w4_asknum_20.json",
        "w6_number_check_20.json",
        "w6_workflow_20.json",
    }:
        raise ValueError("内置黄金集不可覆盖，请使用新文件名")
    item_count = validate_golden_payload(content, runner=runner)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / name
    if path.exists():
        raise ValueError(f"文件已存在: {name}")
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "filename": name,
        "item_count": item_count,
        "version": content.get("version"),
    }
