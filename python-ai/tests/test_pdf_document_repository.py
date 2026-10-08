from unittest.mock import MagicMock

from app.db.pdf_document_repository import upsert_uploaded_pdf_document


def test_annual_report_metadata_uses_doc_id_when_filename_is_storage_hash():
    conn = MagicMock()
    upsert_uploaded_pdf_document(
        conn,
        doc_id="000333_2024",
        source_filename="sha256:abc.pdf",
        content_type="application/pdf",
        content_hash="sha256:abc",
        bucket="regops-docs",
        object_key="reports/000333_2024/sha256:abc.pdf",
        file_size=123,
        doc_type="annual_report",
    )

    params = conn.cursor.return_value.__enter__.return_value.execute.call_args.args[1]
    assert params[1:3] == ("000333", 2024)
    assert params[-1].obj == ["compliance", "rm"]
