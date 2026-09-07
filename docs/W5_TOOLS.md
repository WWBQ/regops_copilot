# W5 工具合同 / Mock / MCP / Java 边界

> 工具合同稳定。先 Function Calling Schema，再用 MCP 当传输。W6 图只编排这些工具。

## 三层分别是什么

| 层 | 是什么 | 本仓库 |
|---|---|---|
| Tool Calling | 模型选工具、填参数 | `openai_tool_schemas()` / `GET /tools` |
| MCP | 发现和调用的协议 | Python `POST /mcp`：`initialize` · `tools/list` · `tools/call` |
| Java 企业边界 | 部门隔离、JWT/RBAC、maker-checker、金融工具（写草稿不重试） | `/api/tools/**` + `/api/reviews/**` |
| Agent | 多步循环 | **审查对比 Workflow + Checkpoint**（不是每轮 `/chat`） |

## 工具合同

| 工具 | 硬约束 |
|---|---|
| `lookup_metric` | `concepts` 传 1–5 科；只认已通过数字。多科时单科待复核不拖垮其它科；全部不可用才 `stop` |
| `list_scope` | 只列库里有的公司/年/指标 |
| `rag_search` | 低分拒答；必须有 `doc_id` + 页。**Java 不代理** |
| `verify_number` | 对不上就停 |
| `compare_peers` | 逐条 `lookup_metric`，不手算差额 / 比率 |
| `create_review_draft` | 确认后写入 PENDING 草稿；同一 `thread_id` 幂等；不提交 maker-checker |
| `emit_conclusion` | 高风险 `confidence≤0.95`。**Java 不代理** |

不挂：`execute_sql`、手算比率、联网补数。`wired_to_chat=true`（点名选工具或开放决策才进 Function Calling，见 [`W6_GRAPH.md`](./W6_GRAPH.md)）。两家+结论仍走 LangGraph Workflow，单问营收仍走问数。

## w5-2 Mock

`backend=mock`（请求体 / `_meta` / `X-Regops-Tool-Backend`）不连库、不连 Java。

| 场景 | 怎么触发 |
|---|---|
| 无数据 | 查 `300750`，或 `inject=missing` |
| 越权 | `dept=research` 查 `000333` |
| 超时 | `inject=timeout`（立刻返回，不 sleep） |
| 重复请求 | 相同 `idempotency_key` → `replayed=true` |

`research` 只能看 002594 / 601633；`compliance` 看五家金样本。Python mock 允许不带 dept；**Java 入口必须带 `X-Regops-Dept`**。

## w5-3 MCP 最小闭环

JSON-RPC 2.0 子集（不是完整 stdio/SSE SDK，也不是 Java MCP Server）：

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

协议错误走 JSON-RPC `error`。工具业务失败（越权/无数据）走 `result.isError=true`。

## w5-4 Java 金融工具（部门隔离）

部门隔离在 Java 先做，再调 Python `/tools/invoke`。不在 Java 重写 `fin_metric` SQL，也不把 RAG 再包一层。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tools/capabilities` | 能力树（不经 Python） |
| GET | `/api/tools/schema/{name}` | 单工具 Schema |
| POST | `/api/tools/lookup` | 查数 |
| POST | `/api/tools/compare` | 同业并列查数 |
| POST | `/api/tools/scope` | 覆盖面 |
| POST | `/api/tools/verify` | 核对金额 |
| POST | `/api/tools/review-draft` | 写入 PENDING 草稿（不重试）；mock 后端仍拒绝 |
| GET | `/api/tools/review-drafts` | 按部门列出草稿 |
| GET | `/api/tools/review-drafts/{draftId}` | 按 `public_id` 取草稿；跨部门 404 |
| POST | `/api/tools/invoke` | 专家通道；拒绝 `rag_search` |

缺部门 / 跨部门 → HTTP 403 + `error_code=unauthorized`。非法参数 → 400。业务缺数仍是 200 + `ok=false`。

```bash
curl -s -X POST http://localhost:8080/api/tools/lookup \
  -H 'Content-Type: application/json' -H 'X-Regops-Dept: research' \
  -d '{"company_code":"000333","concept":"revenue","year":2024,"backend":"mock"}'
```

## w5-5 跨服务安全与韧性

| 项 | 做法 |
|---|---|
| 服务身份 | Java → Python 带 `X-Regops-Service` + `X-Regops-Service-Token` |
| Token 边界 | **不**把用户 `Authorization` 转给 Python |
| 追踪 | `X-Request-ID` + `X-Regops-Dept` |
| 读重试 | 5xx / 网关失败最多再试 `read-retry-count`（默认 2） |
| 写 | `create_review_draft` 落 PENDING，Java `exchange` **不**走读重试 |
| PII | 工具入参日志脱敏（身份证 / 手机号 / 账号） |

Python：未配置 `REGOPS_SERVICE_TOKEN` 时不强制；带了 `X-Regops-Service` 但票不对 → 401。本地 curl 不带头仍可用。

## w5-6 自省与纪律

- Python：`GET /tools/capabilities`、`GET /tools/schema/{name}`
- Java：`GET /api/tools/capabilities`、`GET /api/tools/schema/{name}`
- 规则：[`docs/AGENT_RULES.md`](./AGENT_RULES.md)（含超预算必须停、`error_code=budget_exceeded`）
- 6 维自评：仓库 README

## 不做什么

- 不把 `/chat` 每轮丢进 Function Calling / MCP；工具自选有入口门禁。经营概况一次 `lookup_metric`（`concepts` 最多 5 科），总调用最多 6 次
- 不上开放 ReAct 替代问数或 W6 固定 DAG
- Java 不做 MCP Server（REST 就是企业工具面）
- 不把用户 JWT 透传给 Python（登录只在 Java）
