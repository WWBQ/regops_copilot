from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.labeling.items import json_safe, load_items
from app.labeling.options import task_label_options

TASK_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class LabelStoreError(Exception):
    pass


class LabelStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.root / "tasks.json"
        self.pdf_root = self.root / "pdfs"
        self.pdf_root.mkdir(parents=True, exist_ok=True)
        self._tasks_lock = Lock()
        self._report_locks: dict[str, Lock] = {}
        self._report_guard = Lock()

    def _report_lock(self, path: Path) -> Lock:
        key = str(path)
        with self._report_guard:
            if key not in self._report_locks:
                self._report_locks[key] = Lock()
            return self._report_locks[key]

    @staticmethod
    def valid_task_id(task_id: str) -> bool:
        return bool(TASK_ID_RE.fullmatch(task_id or ""))

    def atomic_write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)

    def list_tasks(self) -> list[dict[str, Any]]:
        if not self.tasks_file.exists():
            return []
        try:
            text = self.tasks_file.read_text(encoding="utf-8").strip()
            if not text:
                return []
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError) as exc:
            raise LabelStoreError("任务列表文件损坏，已停止写入以免清空数据") from exc

    def save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self.atomic_write_json(self.tasks_file, tasks)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if not self.valid_task_id(task_id):
            return None
        for task in self.list_tasks():
            if task.get("id") == task_id:
                return task
        return None

    def resolve(self, rel: str) -> Path:
        path = Path(rel)
        if not path.is_absolute():
            path = self.root / path
        return path

    def load_report(self, task: dict[str, Any]) -> dict[str, Any]:
        report_path = self.resolve(task["report_path"])
        if not report_path.exists():
            return {}
        text = report_path.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        data = json.loads(text)
        return data if isinstance(data, dict) else {}

    def compute_progress(self, task: dict[str, Any]) -> int:
        count = int(task.get("count") or 0)
        if count <= 0:
            return 0
        report = self.load_report(task)
        done = sum(
            1
            for entry in report.values()
            if isinstance(entry, dict) and entry.get("status")
        )
        return round(done / count * 100)

    def with_progress(self, task: dict[str, Any]) -> dict[str, Any]:
        out = dict(task)
        out["progress"] = self.compute_progress(task)
        out["label_options"] = task_label_options(task)
        return out

    def create_task(
        self,
        *,
        name: str,
        desc: str,
        url_type: str,
        filename: str,
        content: bytes,
        label_options: list[str],
    ) -> dict[str, Any]:
        if Path(filename).suffix.lower() != ".xlsx":
            raise ValueError("只接受标准模板 .xlsx，请先下载模板再填写上传")
        task_id = uuid.uuid4().hex
        folder = self.root / task_id
        folder.mkdir(parents=True, exist_ok=True)
        data_path = folder / "data.xlsx"
        report_path = folder / "report.json"
        data_path.write_bytes(content)
        try:
            items = load_items(data_path, url_type)
        except Exception:
            for leftover in folder.glob("*"):
                leftover.unlink(missing_ok=True)
            folder.rmdir()
            raise
        new_task = {
            "id": task_id,
            "name": name,
            "desc": desc,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "data_path": str(data_path.relative_to(self.root)),
            "report_path": str(report_path.relative_to(self.root)),
            "count": len(items),
            "progress": 0,
            "url_type": url_type,
            "label_options": label_options,
        }
        with self._tasks_lock:
            tasks = self.list_tasks()
            tasks.append(new_task)
            self.save_tasks(tasks)
        return self.with_progress(new_task)

    def list_items(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        items = load_items(self.resolve(task["data_path"]), task.get("url_type", "pdf"))
        report = self.load_report(task)
        for item in items:
            entry = report.get(str(item["index"]), {})
            item["status"] = entry.get("status", "")
            item["notes"] = entry.get("notes", "")
            item["taskId"] = task["id"]
            if entry.get("text"):
                item["text"] = entry["text"]
        return items

    def get_item(self, task: dict[str, Any], idx: int) -> dict[str, Any]:
        items = self.list_items(task)
        if idx < 0 or idx >= len(items):
            raise IndexError("index out of range")
        item = items[idx]
        item["total"] = len(items)
        item["label_options"] = task_label_options(task)
        return item

    def save_item(self, task: dict[str, Any], idx: int, data: dict[str, Any]) -> dict[str, Any]:
        report_path = self.resolve(task["report_path"])
        fields = ("id", "text", "otext", "url", "type", "info", "status", "notes")
        with self._report_lock(report_path):
            report = self.load_report(task)
            key = str(idx)
            entry = dict(report.get(key, {}))
            for field in fields:
                if field in data:
                    entry[field] = json_safe(data.get(field, ""))
                elif field not in entry:
                    entry[field] = ""
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            report[key] = entry
            self.atomic_write_json(report_path, report)
            return entry

    def export_rows(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        report = self.load_report(task)
        rows = []
        for idx, entry in report.items():
            row = dict(entry)
            row["index"] = idx
            rows.append(row)
        return rows

    def pdf_path(self, task_id: str, filename: str) -> Path:
        return self.pdf_root / task_id / filename
