-- 解析 JSON 回溯字段（已有 w2_tables 的库执行一次）
ALTER TABLE pdf_document
    ADD COLUMN IF NOT EXISTS parse_object_key VARCHAR(512);

ALTER TABLE web_document
    ADD COLUMN IF NOT EXISTS parse_object_key VARCHAR(512);

COMMENT ON COLUMN pdf_document.parse_object_key IS 'ObjectStore 路径：parsed/pdf/{doc_id}/{content_hash}.parse.json';
COMMENT ON COLUMN web_document.parse_object_key IS 'ObjectStore 路径：parsed/web/{doc_id}/{content_hash}.parse.json';
