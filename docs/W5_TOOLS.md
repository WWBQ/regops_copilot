# W5 工具合同 / Mock / MCP / Java 边界

> 工具合同稳定。先 Function Calling Schema，再用 MCP 当传输。W6 图只编排这些工具。

## 三层分别是什么

| 层 | 是什么 | 本仓库 |
|---|---|---|
| Tool Calling | 模型选工具、填参数 | `openai_tool_schemas()` / `GET /tools` |
| MCP | 发现和调用的协议 | Python `POST /mcp`：`initialize` · `tools/list` · `tools/call` |
| Java 企业边界 | 部门隔离、服务身份、只读金融工具 | `/api/tools/**` |
| Agent | 多步循环 | **还没做**（W6） |

## 工具合同

| 工具 | 硬约束 |
|---|---|
| `lookup_metric` | 只认已通过数字；缺了 `stop` |
| `list_scope` | 只列库里有的公司/年/指标 |
| `rag_search` | 低分拒答；必须有 `doc_id` + 页。**Java 不代理** |
| `verify_number` | 对不上就停 |
| `compare_peers` | 逐条 `lookup_metric`，不手算差额 / 比率 |
| `create_review_draft` | 只暴露合同，`ok=false` / `forbidden_write`，不落库 |
| `emit_conclusion` | 高风险 `confidence≤0.95`。**Java 不代理** |

不挂：`execute_sql`、手算比率、联网补数。`/chat` 仍走问数模板，`wired_to_chat=false`。

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

## w5-4 Java 只读金融工具

部门隔离在 Java 先做，再调 Python `/tools/invoke`。不在 Java 重写 `fin_metric` SQL，也不把 RAG 再包一层。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tools/capabilities` | 能力树（不经 Python） |
| GET | `/api/tools/schema/{name}` | 单工具 Schema |
| POST | `/api/tools/lookup` | 查数 |
| POST | `/api/tools/compare` | 同业并列查数 |
| POST | `/api/tools/scope` | 覆盖面 |
| POST | `/api/tools/verify` | 核对金额 |
| POST | `/api/tools/review-draft` | 写操作拒绝 |
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
| 写 | `create_review_draft` 不落库、不重试 |
| PII | 工具入参日志脱敏（身份证 / 手机号 / 账号） |

Python：未配置 `REGOPS_SERVICE_TOKEN` 时不强制；带了 `X-Regops-Service` 但票不对 → 401。本地 curl 不带头仍可用。

## w5-6 自省与纪律

- Python：`GET /tools/capabilities`、`GET /tools/schema/{name}`
- Java：`GET /api/tools/capabilities`、`GET /api/tools/schema/{name}`
- 规则：[`docs/AGENT_RULES.md`](./AGENT_RULES.md)
- 6 维自评：仓库 README

## 不做什么

- 不上 LangGraph，不把 `/chat` 每轮丢进 MCP
- Java 不做 MCP Server（REST 就是企业工具面）
- 不把用户 JWT 透传给 Python（W7 再做登录）
