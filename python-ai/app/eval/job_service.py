"""评测任务后台执行与报告持久化。"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.eval.ab_runner import run_ab_eval
from app.eval.asknum_runner import run_asknum_eval
from app.eval.compliance_schema_runner import run_compliance_schema_eval
from app.eval.number_check_runner import run_number_check_eval
from app.eval.rag_guard_runner import run_rag_guard_eval
from app.eval.rag_compare_runner import run_rag_compare_eval
from app.eval.rag_retrieval_runner import run_rag_retrieval_eval
from app.eval.rag_support_runner import run_rag_support_eval
from app.eval.registry import REPORTS_DIR, get_task, task_to_dict
from app.eval.selection import normalize_categories, normalize_item_ids, select_items
from app.eval.strategy_runner import run_strategy_eval
from app.eval.w1_chat_runner import resolve_eval_chat_model, run_w1_chat_eval
from app.models.llm import list_available_models

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_runs: set[str] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_dir(task_id: str, run_id: str) -> Path:
    return REPORTS_DIR / task_id / run_id


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_tasks() -> list[dict[str, Any]]:
    from app.eval.registry import load_all_tasks

    return [task_to_dict(task) for task in load_all_tasks().values()]


def _infer_run_model(meta: dict[str, Any], run_dir: Path) -> str | None:
    params = meta.get("params") or {}
    raw = params.get("model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    summary = meta.get("summary") or {}
    raw = summary.get("model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    report = _read_json(run_dir / "report.json")
    if not report:
        return None
    raw = (report.get("params") or {}).get("model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    results = report.get("results") or []
    if results and isinstance(results[0].get("model"), str) and results[0]["model"].strip():
        return results[0]["model"].strip()
    return None


def _serialize_run_meta(meta: dict[str, Any], *, include_report: bool = False) -> dict[str, Any]:
    params = dict(meta.get("params") or {})
    run_dir = _run_dir(meta["task_id"], meta["run_id"])
    inferred = _infer_run_model(meta, run_dir)
    if inferred:
        params["model"] = inferred
    row = {
        "run_id": meta["run_id"],
        "task_id": meta["task_id"],
        "status": meta["status"],
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "progress": meta.get("progress") or {"done": 0, "total": 0, "current_id": None},
        "params": params,
        "error": meta.get("error"),
        "summary": meta.get("summary"),
    }
    if include_report and meta.get("status") == "completed":
        report_path = _run_dir(meta["task_id"], meta["run_id"]) / "report.json"
        report = _read_json(report_path)
        if report:
            row["report"] = report
    return row


def list_runs(*, task_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    _scan_reports_from_disk()
    rows: list[dict[str, Any]] = []
    if not REPORTS_DIR.is_dir():
        return rows

    task_dirs = [REPORTS_DIR / task_id] if task_id else sorted(REPORTS_DIR.iterdir())
    for task_path in task_dirs:
        if not task_path.is_dir():
            continue
        for run_path in sorted(task_path.iterdir(), reverse=True):
            if not run_path.is_dir():
                continue
            meta = _read_json(run_path / "meta.json")
            if meta:
                rows.append(_serialize_run_meta(meta))
    rows.sort(key=lambda row: row.get("started_at") or "", reverse=True)
    if task_id:
        rows = [row for row in rows if row["task_id"] == task_id]
    return rows[:limit]


def get_run(run_id: str, *, include_report: bool = False) -> dict[str, Any] | None:
    _scan_reports_from_disk()
    for task_path in REPORTS_DIR.iterdir() if REPORTS_DIR.is_dir() else []:
        if not task_path.is_dir():
            continue
        meta_path = task_path / run_id / "meta.json"
        if meta_path.is_file():
            meta = _read_json(meta_path)
            if meta:
                return _serialize_run_meta(meta, include_report=include_report)
    return None


def _find_run_meta_path(run_id: str) -> Path | None:
    if not REPORTS_DIR.is_dir():
        return None
    for task_path in REPORTS_DIR.iterdir():
        if not task_path.is_dir():
            continue
        meta_path = task_path / run_id / "meta.json"
        if meta_path.is_file():
            return meta_path
    return None


def delete_run(run_id: str) -> None:
    meta_path = _find_run_meta_path(run_id)
    if meta_path is None:
        raise KeyError(f"eval run not found: {run_id}")

    meta = _read_json(meta_path) or {}
    if meta.get("status") == "running":
        raise RuntimeError("运行中的报告不可删除")

    with _lock:
        if run_id in _active_runs:
            raise RuntimeError("运行中的报告不可删除")

    run_dir = meta_path.parent
    shutil.rmtree(run_dir)
    logger.info("deleted eval run run_id=%s task_id=%s", run_id, meta.get("task_id"))


def create_task(**kwargs: Any) -> dict[str, Any]:
    from app.eval.registry import create_task as registry_create_task, task_to_dict

    task = registry_create_task(**kwargs)
    return task_to_dict(task)


def delete_task(task_id: str) -> None:
    from app.eval.registry import delete_task as registry_delete_task

    with _lock:
        for run_id in _active_runs:
            row = get_run(run_id, include_report=False)
            if row and row.get("task_id") == task_id:
                raise RuntimeError("该任务有运行中的评测，无法删除")

    registry_delete_task(task_id)


def _scan_reports_from_disk() -> None:
    """占位：报告均通过 meta.json 读取，无需内存索引。"""
    return None


def _update_meta(task_id: str, run_id: str, **fields: Any) -> dict[str, Any]:
    meta_path = _run_dir(task_id, run_id) / "meta.json"
    meta = _read_json(meta_path) or {}
    meta.update(fields)
    _write_json(meta_path, meta)
    return meta


def _execute_run(task_id: str, run_id: str, params: dict[str, Any]) -> None:
    task = get_task(task_id)
    run_path = _run_dir(task_id, run_id)

    def on_progress(done: int, total: int, current_id: str) -> None:
        _update_meta(
            task_id,
            run_id,
            progress={"done": done, "total": total, "current_id": current_id},
        )

    try:
        if task.runner == "w1_chat":
            settings = get_settings()
            base_url = params.get("base_url") or settings.eval_chat_base_url
            report = run_w1_chat_eval(
                golden_path=task.golden_path,
                base_url=base_url,
                limit=int(params.get("limit") or 0),
                model=params.get("model") or None,
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                temperature=params.get("temperature"),
                on_progress=on_progress,
            )
        elif task.runner == "rag_retrieval":
            report = run_rag_retrieval_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                top_k=int(params.get("top_k") or 0),
                on_progress=on_progress,
            )
        elif task.runner == "compliance_schema":
            report = run_compliance_schema_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        elif task.runner == "w4_asknum":
            report = run_asknum_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        elif task.runner == "w6_number_check":
            report = run_number_check_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        elif task.runner == "w8_strategy":
            report = run_strategy_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        elif task.runner == "w8_ab":
            report = run_ab_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        elif task.runner == "rag_support":
            report = run_rag_support_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                top_k=int(params.get("top_k") or 0),
                on_progress=on_progress,
            )
        elif task.runner in {"rag_acl", "rag_refuse"}:
            report = run_rag_guard_eval(
                golden_path=task.golden_path,
                task_id=task.runner,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        elif task.runner == "rag_compare":
            report = run_rag_compare_eval(
                golden_path=task.golden_path,
                limit=int(params.get("limit") or 0),
                categories=params.get("categories") or None,
                item_ids=params.get("item_ids") or None,
                on_progress=on_progress,
            )
        else:
            raise ValueError(f"unsupported runner: {task.runner}")

        _write_json(run_path / "report.json", report)
        _update_meta(
            task_id,
            run_id,
            status="completed",
            finished_at=_now_iso(),
            summary=report.get("summary"),
            progress={
                "done": len(report.get("results") or []),
                "total": len(report.get("results") or []),
                "current_id": None,
            },
            error=None,
        )
        logger.info("eval run completed task=%s run=%s", task_id, run_id)
    except Exception as exc:
        logger.exception("eval run failed task=%s run=%s", task_id, run_id)
        _update_meta(
            task_id,
            run_id,
            status="failed",
            finished_at=_now_iso(),
            error=str(exc),
        )
    finally:
        with _lock:
            _active_runs.discard(run_id)


def start_run(
    *,
    task_id: str,
    limit: int = 0,
    category: str = "",
    categories: list[str] | None = None,
    item_ids: list[str] | None = None,
    top_k: int = 0,
    model: str = "",
    temperature: float | None = None,
) -> dict[str, Any]:
    task = get_task(task_id)
    if not task.golden_path.is_file():
        raise FileNotFoundError(f"golden set missing: {task.golden_file}")

    resolved_categories = normalize_categories(category, categories)
    resolved_item_ids = normalize_item_ids(item_ids)
    resolved_model: str | None = None
    if task.runner == "w1_chat":
        settings = get_settings()
        resolved_model = resolve_eval_chat_model(
            model,
            available=list_available_models(settings),
            default_model=settings.default_model,
        )

    with _lock:
        if len(_active_runs) >= 1:
            raise RuntimeError("已有评测任务在运行，请等待完成后再启动")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{uuid4().hex[:6]}"
    params = {
        "limit": limit,
        "categories": resolved_categories or None,
        "item_ids": resolved_item_ids or None,
        "top_k": top_k or None,
        "model": resolved_model,
        "temperature": temperature,
        "use_rag": False if task.runner == "w1_chat" else None,
    }

    import json as json_lib

    golden_payload = json_lib.loads(task.golden_path.read_text(encoding="utf-8"))
    planned_items = select_items(
        golden_payload.get("items") or [],
        categories=resolved_categories,
        item_ids=resolved_item_ids,
        limit=limit,
    )
    if not planned_items:
        raise ValueError("没有匹配的评测题，请检查题型或题号")
    planned_total = len(planned_items)

    meta = {
        "run_id": run_id,
        "task_id": task_id,
        "status": "running",
        "started_at": _now_iso(),
        "finished_at": None,
        "progress": {"done": 0, "total": planned_total, "current_id": None},
        "params": params,
        "summary": None,
        "error": None,
    }
    _write_json(_run_dir(task_id, run_id) / "meta.json", meta)

    with _lock:
        _active_runs.add(run_id)

    thread = threading.Thread(
        target=_execute_run,
        args=(task_id, run_id, params),
        name=f"eval-{task_id}-{run_id}",
        daemon=True,
    )
    thread.start()
    return _serialize_run_meta(meta)


def is_run_active(run_id: str) -> bool:
    with _lock:
        return run_id in _active_runs
