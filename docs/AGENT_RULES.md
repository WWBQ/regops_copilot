# Agent 规则（w5-6）

给 Agent 用，不是给人看的帮助文档。调用方必须遵守；违反即停。

## 禁止

1. **不得绕过工具直连 HTTP / 数据库 / 搜索补数。** 只调已发现的命令。
2. **不得客户端截断或正则抠数字。** 过滤、分页、精度只认服务端字段。
3. **不得执行 SQL，不得手算 ROE / 毛利率 / 同比差额。**
4. **不得在 `ok=false` 或 `stop=true` 之后改用模型编造。**
5. **不得把 `human_review` / 缺失当成 0 或「差不多」。** 必须显式写「未入库 / 待复核」。

## 必须

1. 未知公司或指标：先 `list_scope`，再用返回的短名去 `lookup_metric`。
2. 叙述题走 `rag_search`；引用必须带 `doc_id` 和 `page≥1`。
3. 声称金额必须 `verify_number`，对不上就停。
4. 结论走 `emit_conclusion`；不合规 Schema 直接拒绝，不提示「再试一次凑过校验」。
5. 写操作 `create_review_draft` 本周不落库；不要重试写。
6. 每个任务查 `capabilities` / `schema` 至多一次，不要靠读文档探索。

## 发现

- 能力树：`GET /tools/capabilities` 或 `GET /api/tools/capabilities`
- 单工具 Schema：`GET /tools/schema/{name}`
- MCP：`tools/list` / `tools/call`

## 和人用 API 的差别

人可以打开质量页慢慢点。Agent 必须能从机器可读 Schema 发现参数，且错误码稳定（`missing` / `unauthorized` / `timeout` / `forbidden_write`）。
