from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

from app.documents.service import UploadResult
from app.ingest.chunker import TextChunk
from app.ingest.models import PageBlock
from app.ingest.pipeline import IngestResult, ingest_pdf_to_vectors


def test_ingest_pdf_to_vectors_writes_job_stages(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "002594_2024.pdf"
    pdf.write_bytes(b"%PDF-1.4 demo")
    statuses: list[str] = []
    block = PageBlock(
        page_no=1,
        text="本集团研发投入约为542亿元。",
        tables=[],
        source_file=pdf.name,
        content_hash="sha256:abc",
    )
    upload = UploadResult(
        doc_id="002594_2024",
        bucket="regops-docs",
        object_key="reports/002594_2024/sha256:abc.pdf",
        content_hash="sha256:abc",
        source_filename=pdf.name,
        size=pdf.stat().st_size,
        reused=False,
    )

    class FakeService:
        def upload_pdf(self, *_a, **_k):
            return upload

        def save_parse_artifact(self, *_a, **_k):
            return "parses/002594_2024.json"

    class FakeParseStore:
        def exists(self, *_a, **_k):
            return False

        def save_blocks(self, *_a, **_k):
            return "parses/key", b"{}"

        def object_key_for(self, *_a, **_k):
            return "parses/key"

    class FakeConn:
        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    @contextmanager
    def fake_conn():
        yield FakeConn()

    monkeypatch.setattr("app.ingest.pipeline._build_document_service", lambda: FakeService())
    monkeypatch.setattr("app.ingest.pipeline.LocalObjectStore", lambda *_a, **_k: object())
    monkeypatch.setattr("app.ingest.pipeline.ParseArtifactStore", lambda *_a, **_k: FakeParseStore())
    monkeypatch.setattr("app.ingest.pipeline.create_job", lambda *_a, **_k: "job-1")
    monkeypatch.setattr(
        "app.ingest.pipeline.update_job_status",
        lambda *_a, **kwargs: statuses.append(kwargs["status"]),
    )
    monkeypatch.setattr("app.ingest.pipeline.get_connection", fake_conn)
    monkeypatch.setattr("app.ingest.pipeline.parse_pdf", lambda _p: [block])
    monkeypatch.setattr("app.ingest.pipeline.clean_page_blocks", lambda blocks: (blocks, None))
    monkeypatch.setattr(
        "app.ingest.pipeline.chunk_page_blocks",
        lambda *_a, **_k: [
            TextChunk(doc_id="002594_2024", chunk_index=0, content="本集团研发投入", metadata={"page": 1})
        ],
    )
    monkeypatch.setattr("app.ingest.pipeline.get_embedding_model", lambda: object())
    monkeypatch.setattr("app.ingest.pipeline.embed_texts", lambda *_a, **_k: [[0.1] * 8])
    monkeypatch.setattr("app.ingest.pipeline.delete_chunks", lambda *_a, **_k: 0)
    monkeypatch.setattr("app.ingest.pipeline.insert_chunks", lambda *_a, **_k: 1)
    monkeypatch.setattr("app.ingest.pipeline.upsert_pdf_document", lambda *_a, **_k: None)
    monkeypatch.setattr("app.ingest.pipeline.content_hash", lambda _p: "sha256:abc")

    result = ingest_pdf_to_vectors(pdf, doc_id="002594_2024")
    assert isinstance(result, IngestResult)
    assert result.job_id == "job-1"
    assert result.chunks == 1
    assert statuses == ["PARSING", "CLEANING", "CHUNKING", "EMBEDDING", "DONE"]


def test_ingest_pdf_to_vectors_marks_failed(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "002594_2024.pdf"
    pdf.write_bytes(b"%PDF-1.4 demo")
    statuses: list[str] = []

    class FakeService:
        def upload_pdf(self, *_a, **_k):
            raise RuntimeError("upload boom")

    monkeypatch.setattr("app.ingest.pipeline._build_document_service", lambda: FakeService())
    monkeypatch.setattr("app.ingest.pipeline.LocalObjectStore", lambda *_a, **_k: object())
    monkeypatch.setattr("app.ingest.pipeline.ParseArtifactStore", lambda *_a, **_k: object())
    monkeypatch.setattr("app.ingest.pipeline.create_job", lambda *_a, **_k: "job-fail")
    monkeypatch.setattr(
        "app.ingest.pipeline.update_job_status",
        lambda *_a, **kwargs: statuses.append(kwargs["status"]),
    )

    @contextmanager
    def fake_conn():
        yield MagicMock()

    monkeypatch.setattr("app.ingest.pipeline.get_connection", fake_conn)

    try:
        ingest_pdf_to_vectors(pdf, doc_id="002594_2024")
        raise AssertionError("expected failure")
    except RuntimeError as exc:
        assert "upload boom" in str(exc)
    assert statuses == ["FAILED"]
