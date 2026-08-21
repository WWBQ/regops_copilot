"""会话 API 与 RAG chat 集成测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_document_service
from app.ingest.session_pipeline import SessionIngestResult
from app.main import app
from app.models.base import ChatResult, LLMClient
from app.rag.service import Citation as RagCitation
from app.rag.service import RagAnswer


class FakeLLMClient(LLMClient):
    async def chat(self, messages, *, temperature=0.1) -> str:
        return "基于文档的 mock 回复"

    async def chat_with_usage(self, messages, *, temperature=0.1) -> ChatResult:
        return ChatResult(content="基于文档的 mock 回复", prompt_tokens=1, completion_tokens=2)


class FakeUploadResult:
    doc_id = "sess_test_abcd1234"
    bucket = "regops-docs"
    object_key = "temp/sessions/x/y.pdf"
    content_hash = "sha256:abcd1234"
    source_filename = "demo.pdf"
    size = 28
    reused = False


class FakeDocumentService:
    def viewer_url(self, doc_id: str, *, page: int | None = None, expires_in: int = 300) -> str:
        return f"http://test/doc/{doc_id}#page={page}"

    def upload_session_pdf(self, body: bytes, source_filename: str, *, session_id: str) -> FakeUploadResult:
        return FakeUploadResult()


def _tables_ready() -> bool:
    try:
        from app.db.connection import get_connection

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.chat_session')")
                return cur.fetchone()[0] is not None
    except Exception:
        return False


requires_session_db = pytest.mark.skipif(not _tables_ready(), reason="chat_session tables missing")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr("app.api.chat.get_llm_client", lambda settings, model=None: FakeLLMClient())
    monkeypatch.setattr("app.api.chat.list_available_models", lambda settings=None: ["deepseek"])
    app.dependency_overrides[get_document_service] = lambda: FakeDocumentService()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.anyio
@requires_session_db
async def test_create_session(client: AsyncClient):
    response = await client.post("/sessions")
    assert response.status_code == 200
    body = response.json()
    assert "session_id" in body


@pytest.mark.anyio
@requires_session_db
async def test_upload_session_document_queues_job(client: AsyncClient):
    create = await client.post("/sessions")
    session_id = create.json()["session_id"]
    pdf_bytes = b"%PDF-1.4\n% minimal pdf stub\n"

    with patch("app.api.sessions.ingest_session_pdf") as mock_ingest:
        mock_ingest.return_value = SessionIngestResult(
            doc_id="sess_test",
            pages=1,
            chunks=1,
            parse_cached=False,
        )
        response = await client.post(
            f"/sessions/{session_id}/documents",
            files={"file": ("demo.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "PENDING"
    assert body["doc_id"].startswith("sess_")


@pytest.mark.anyio
async def test_chat_with_session_pending_docs(client: AsyncClient):
    if not _tables_ready():
        pytest.skip("chat_session tables missing")

    create = await client.post("/sessions")
    session_id = create.json()["session_id"]
    pdf_bytes = b"%PDF-1.4\n% minimal pdf stub\n"

    with patch("app.api.sessions.ingest_session_pdf"), patch(
        "app.api.chat.collect_rag_doc_ids", return_value=[]
    ):
        upload = await client.post(
            f"/sessions/{session_id}/documents",
            files={"file": ("demo.pdf", pdf_bytes, "application/pdf")},
        )
        assert upload.status_code == 200

        chat = await client.post(
            "/chat",
            json={"message": "营收多少？", "session_id": session_id, "use_rag": True},
        )
    assert chat.status_code == 200
    assert "解析入库中" in chat.json()["reply"]


@pytest.mark.anyio
async def test_chat_with_session_rag(client: AsyncClient):
    if not _tables_ready():
        pytest.skip("chat_session tables missing")

    create = await client.post("/sessions")
    session_id = create.json()["session_id"]
    rag = RagAnswer(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}],
        citations=[
            RagCitation(doc_id="sess_demo", page=3, snippet="片段", viewer_url="http://x#page=3")
        ],
        doc_ids=["sess_demo"],
    )

    with patch("app.api.chat.session_exists", return_value=True), patch(
        "app.api.chat.list_session_documents", return_value=[]
    ), patch(
        "app.api.chat.prepare_chat_rag", return_value=rag
    ):
        chat = await client.post(
            "/chat",
            json={"message": "营收多少？", "session_id": session_id, "use_rag": True},
        )

    assert chat.status_code == 200
    body = chat.json()
    assert body["rag_used"] is True
    assert len(body["citations"]) == 1
    assert body["citations"][0]["page"] == 3
