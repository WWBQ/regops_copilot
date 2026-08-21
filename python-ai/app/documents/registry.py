"""文档入库：object_key 注册表（W2-4 前用 JSON，之后可换 PostgreSQL）。"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DocumentRecord:
    doc_id: str
    bucket: str
    object_key: str
    content_hash: str
    source_filename: str
    content_type: str
    size: int
    created_at: str
    updated_at: str
    parse_object_key: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> DocumentRecord:
        data = dict(raw)
        data.setdefault("parse_object_key", None)
        return cls(**data)


class DocumentRegistry:
    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.is_file():
            self._save({})

    def _load(self) -> dict[str, dict]:
        if not self.registry_path.is_file():
            return {}
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, dict]) -> None:
        self.registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, doc_id: str) -> DocumentRecord | None:
        raw = self._load().get(doc_id)
        if raw is None:
            return None
        return DocumentRecord.from_dict(raw)

    def upsert(self, record: DocumentRecord) -> DocumentRecord:
        data = self._load()
        now = datetime.now(tz=UTC).isoformat()
        existing = data.get(record.doc_id)
        if existing:
            record.created_at = existing.get("created_at", now)
        else:
            record.created_at = now
        record.updated_at = now
        data[record.doc_id] = record.to_dict()
        self._save(data)
        logger.info("document upsert doc_id=%s key=%s", record.doc_id, record.object_key)
        return record

    def list_all(self) -> list[DocumentRecord]:
        return [DocumentRecord.from_dict(raw) for raw in self._load().values()]
