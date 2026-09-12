-- 回填年报 dept_acl（与 Java DeptAcl / python-ai dept_scope 对齐）。
-- 运行时检索过滤按 doc_id 前缀（002594_2024），不依赖本列；本列给运维查看与后续 SQL 过滤用。
--   psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w3_dept_acl.sql

UPDATE pdf_document
SET dept_acl = CASE company_code
    WHEN '002594' THEN '["compliance", "research"]'::jsonb
    WHEN '601633' THEN '["compliance", "research"]'::jsonb
    WHEN '000333' THEN '["compliance", "rm"]'::jsonb
    WHEN '000651' THEN '["compliance", "rm"]'::jsonb
    WHEN '600031' THEN '["compliance"]'::jsonb
    WHEN '300750' THEN '["compliance"]'::jsonb
    WHEN '600519' THEN '["compliance"]'::jsonb
    ELSE '[]'::jsonb
END,
    updated_at = NOW()
WHERE company_code IS NOT NULL;
