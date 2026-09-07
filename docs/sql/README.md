# SQL 迁移说明

## 文件

| 文件 | 说明 |
|------|------|
| `init_pgvector.sql` | 扩展 + `doc_chunks`（含 `source_type`） |
| `w2_tables.sql` | W2：`pdf_document` / `web_document` / `ingest_job` / `fin_metric` + `doc_chunks` 补丁 |
| `w3_chat_sessions.sql` | W3：`chat_session` / `session_document` |
| `w4_rag_query_log.sql` | W3：RAG 检索 trace 日志 `rag_query_log` |
| `w4_asknum_query_log.sql` | W4：问数 trace 日志 `asknum_query_log` |
| `w4_asknum_alias.sql` | W4：问数/检索别名 `asknum_alias`（近义词 → 指标或证券代码） |
| `w6_review_draft.sql` | W6-4：`review_draft`（Agent 只写 `PENDING`；`thread_id` / `idempotency_key` 部分唯一） |
| `w7_identity.sql` | W7：工单状态扩到 `SUBMITTED/REVIEWED/REJECTED`；`app_user` / `customer_profile` / `audit_event`；用户由 Java 种子写入 |

## 新库（Docker 首次启动）

`compose.yaml` 已挂载 `01_init.sql` … `08_w7_identity.sql`，`docker compose up -d db` 会自动建表。

## 已有库（之前只跑过 init）

```bash
docker compose exec db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/02_w2_tables.sql
# 或本机：
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w2_tables.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w4_rag_query_log.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w4_asknum_query_log.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w4_asknum_alias.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w6_review_draft.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w7_identity.sql
```

## 验证

```bash
docker compose exec db psql -U regops -d regops_db -c "\dt"
```

应看到：`doc_chunks` `pdf_document` `web_document` `ingest_job` `fin_metric` `rag_query_log` `asknum_query_log` `asknum_alias` `review_draft` `app_user` `customer_profile` `audit_event`

## 解析 JSON 回溯

整份 `PageBlock[]` 存 ObjectStore，路径：

```text
parsed/pdf/{doc_id}/{content_hash}.parse.json
```

`pdf_document.parse_object_key` 指向该文件。保存：

```bash
cd python-ai
python scripts/save_parse_artifact.py --doc-id 002594_2024
# 或直接对 PDF：
python scripts/save_parse_artifact.py ../data/raw/002594_2024_annual.pdf
```
