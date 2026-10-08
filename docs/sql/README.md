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
| `w7_identity.sql` | W7：`app_user`；历史兼容脚本仍含 `audit_event`，当前应用不再读写；用户由 Java 种子写入 |
| `w10_storage_unification.sql` | 已有库升级：同内容会话文档可分别登记，哈希改为普通索引 |
| `w11_chat_history.sql` | 按登录用户持久化合规问答的会话标题和消息 |
| `w12_trace_ownership.sql` | RAG/问数监控 trace 记录用户归属；仅可靠关联到单一会话所有者的旧数据回填，其他旧记录对用户隐藏 |
| `w13_ingest_batches.sql` | 解析任务批次与阶段快照；多个 PDF 可归入同一个任务 |
| `w14_fin_metric_review.sql` | 财务事实人工复核：确认或拒绝，保留原始金额、原因、来源与复核人 |

## 新库（Docker 首次启动）

`compose.yaml` 挂载初始化脚本，`docker compose up -d db` 会自动建表。

## 已有库（之前只跑过 init）

```bash
docker compose exec db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/02_w2_tables.sql
# 或本机：
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w2_tables.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w4_rag_query_log.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w4_asknum_query_log.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w4_asknum_alias.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w7_identity.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w10_storage_unification.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w11_chat_history.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w12_trace_ownership.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w13_ingest_batches.sql
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w14_fin_metric_review.sql
```

## 验证

```bash
docker compose exec db psql -U regops -d regops_db -c "\dt"
```

应看到：`doc_chunks` `pdf_document` `web_document` `ingest_job` `ingest_batch` `ingest_batch_event` `fin_metric` `fin_metric_review` `rag_query_log` `asknum_query_log` `asknum_alias` `app_user` `chat_history`。旧初始化脚本也可能创建已停用的 `audit_event`，不影响当前功能。

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
