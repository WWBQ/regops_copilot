-- 已有数据库升级：允许同一 PDF 被不同会话分别登记，元数据仍以 doc_id 区分。
ALTER TABLE pdf_document
    DROP CONSTRAINT IF EXISTS uk_pdf_document_content_hash;

CREATE INDEX IF NOT EXISTS idx_pdf_document_content_hash
    ON pdf_document (content_hash);
