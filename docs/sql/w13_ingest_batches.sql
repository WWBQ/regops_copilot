-- 一次解析任务可包含多份 PDF；单文件 ingest_job 保留作阶段明细。
CREATE TABLE IF NOT EXISTS ingest_batch (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(160) NOT NULL,
    parser_backend VARCHAR(16) NOT NULL,
    use_parse_cache BOOLEAN NOT NULL DEFAULT TRUE,
    total_files INT NOT NULL CHECK (total_files > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'QUEUED'
        CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'PARTIAL', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

ALTER TABLE ingest_job
    ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES ingest_batch(batch_id);
CREATE INDEX IF NOT EXISTS idx_ingest_job_batch ON ingest_job (batch_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ingest_batch_created ON ingest_batch (created_at DESC);

-- 每次文件阶段变化留一个快照；折线图只从真实事件绘制，不在前端猜进度。
CREATE TABLE IF NOT EXISTS ingest_batch_event (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES ingest_batch(batch_id) ON DELETE CASCADE,
    job_id UUID,
    stage VARCHAR(32) NOT NULL,
    pending_count INT NOT NULL,
    active_count INT NOT NULL,
    done_count INT NOT NULL,
    failed_count INT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ingest_batch_event_time
    ON ingest_batch_event (batch_id, id);
