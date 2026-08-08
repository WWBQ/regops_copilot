-- RegOps Copilot: PostgreSQL + pgvector 初始化
-- 仅在数据卷首次创建时执行

CREATE EXTENSION IF NOT EXISTS vector;

-- RAG 文档块表（embedding 维度与模型一致，默认 1024）
CREATE TABLE IF NOT EXISTS doc_chunks (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    embedding   vector(1024),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON doc_chunks(doc_id);

-- 有向量数据后再建 HNSW 索引；空表建索引也可以
CREATE INDEX IF NOT EXISTS idx_doc_chunks_embedding
ON doc_chunks
USING hnsw (embedding vector_cosine_ops);
