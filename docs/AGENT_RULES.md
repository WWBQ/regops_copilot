# Agent 规则（w5-6）

给 Agent 用，不是给人看的帮助文档。调用方必须遵守；违反即停。

## 禁止

1. **不得绕过工具直连 HTTP / 数据库 / 搜索补数。** 只调已发现的命令。
2. **不得客户端截断或正则抠数字。** 过滤、分页、精度只认服务端字段。
3. **不得执行 SQL，不得手算 ROE / 毛利率 / 同比差额。**
4. **不得在 `ok=false` 或 `stop=true` 之后改用模型编造。**
5. **不得把 `human_review` / 缺失当成 0 或「差不多」。** 必须显式写「未入库 / 待复核」。
6. **不得在终稿写入无法回溯到工具返回或引用片段的数字。** 编排层会抽取并拦截，不靠 Prompt。

## 必须

1. 未知公司或指标：先 `list_scope` **一次**。查数只用 `lookup_metric`，`concepts` 传列表（单科 1 个，概况最多 5 个），不要连调多次。
2. 叙述题走 `rag_search`。`[n]` 角标由编排层插入，不要在正文写 doc_id 长串。
3. 声称金额必须 `verify_number`，对不上就停。
4. 结论走 `emit_conclusion`；不合规 Schema 直接拒绝，不提示「再试一次凑过校验」。
5. 写操作 `create_review_draft` 只在人工确认之后落 PENDING 草稿；不要重试写；同一 `thread_id` 不建第二条。审查对比在 `emit_conclusion` 前会 Checkpoint 暂停，续跑不要重跑查数。取消不落库。不要改成 REVIEWED / REJECTED，也不要提交 maker-checker——那是 Java `/api/reviews/**` 的事。
6. 超过步数 / 工具次数 / 时间 / Token 预算必须明确终止，降级为解释或转人工，不得为了凑完而补调写工具。
7. 每个任务查 `capabilities` / `schema` 至多一次，不要靠读文档探索。
8. `/chat` 默认不进工具循环。进循环的只有：点名选工具、经营概况（无标准指标）、库外科目（研发/毛利率/分红）、待复核或缺失后的追问。写工具仍禁止。单问「是多少」和两家+结论不走循环。
9. 终稿里的金额和百分数必须能对回 `fin_metric` 或引用片段；对不上则降级为〔无证据〕并标明拦截原因（量纲 / 手算 / 无证据）。

## 发现

- 能力树：`GET /tools/capabilities` 或 `GET /api/tools/capabilities`
- 单工具 Schema：`GET /tools/schema/{name}`
- MCP：`tools/list` / `tools/call`

## 和人用 API 的差别

人可以打开质量页慢慢点。Agent 必须能从机器可读 Schema 发现参数，且错误码稳定（`missing` / `unauthorized` / `timeout` / `forbidden_write` / `budget_exceeded`）。
