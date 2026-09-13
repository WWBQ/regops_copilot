# W9-1 端到端双栈集成

> Correlation ID、错误映射、超时预算、依赖降级。五条产品链路经 **Java BFF** 打通。红队 / Langfuse / Compose / K8s / 前端降级见 [`W9_SECURITY.md`](./W9_SECURITY.md) · [`W9_OBS.md`](./W9_OBS.md) · [`W9_COMPOSE.md`](./W9_COMPOSE.md) · [`W9_K8S.md`](./W9_K8S.md) · [`W9_UX.md`](./W9_UX.md)。

## 怎么走

```text
浏览器  ──X-Request-ID──►  java-service(:8080)
                              │  回写响应头 + MDC + extra.request_id
                              │  错误码：upstream_down / upstream_timeout
                              ▼
                         python-ai(:8000)
                              │  中间件注入 / 回写同一 ID，日志带 [request_id]
                              ▼
                         Postgres / 模型
```

降级：Java 自身探活永远 **200**。Python 挂了只把 `pythonAi.status=down` 写进 `/api/health`。登录、复核、审计仍走 Java+Postgres。问答 / 问数 / 工具变成 `502 upstream_down` 或 `504 upstream_timeout`，正文是短句，不是 FastAPI JSON 或堆栈。

## 五条链路

| # | 链路 | 入口 | Owner |
|---|---|---|---|
| 1 | 问答 RAG | `POST /api/chat`（前端流式走 `/api/chat/stream`） | Vue → Java → Python RAG |
| 2 | 问数 | 同一 `/api/chat`，`route=metric*`，命中事实库则 0 token | Vue → Java → Python asknum |
| 3 | 指标查询 | `POST /api/tools/lookup` + `X-Regops-Dept` | Java ACL → Python `lookup_metric` |
| 4 | 工单草稿 | `POST /api/tools/review-draft` | Python 只写 **PENDING** |
| 5 | 双人复核 + 审计 | `/api/reviews/**` + `GET /api/audit/events` | **只 Java**；JWT |

演示账号：`analyst/analyst123` 建单并提交，`checker/checker123` 通过。没有 `APPROVED`。

冒烟（打 Java `:8080`，不打 Python 直连）：

```bash
python-ai/.venv/bin/python eval/run_w9_e2e.py
```

Python 未启动时，1–4 记 `skip`，5 仍须 `pass`。未配模型时 RAG 记 `skip`（503）。

## Correlation ID

请求头 / 响应头都是 **`X-Request-ID`**。

1. 浏览器：`web/src/api/client.ts` 每次 `apiFetch` / `streamChat` 生成 UUID。
2. Java：`RequestIdFilter` 缺则补，写入 MDC，回写响应；`ApiError.extra.request_id` 同步带上。
3. Java → Python：`PythonAiClient` 透传，并带服务身份，**不**转发用户 JWT。
4. Python：ASGI 中间件（不缓冲 SSE）缺则补、回写；日志格式 `%(request_id)s`。`/chat` 的 Header 仍进 RAG trace。
5. 复核审计行有 `request_id`。系统健康页展示「最近关联 ID」。聊天失败会把 ID 写进回复。

本地开发时 Vite 把 `/api/**`（含 `/api/chat/stream`）代理到 Java。SSE 走 `StreamingResponseBody`，Spring 二次派发的 dispatcher 是 `ASYNC`，必须 `permitAll`，否则问答会 401「未登录」。质量页 `/api/ops/quality` 仍可直连 Python，与本周无关。

## 错误映射

| 情况 | HTTP | `extra.error_code` | `detail` |
|---|---|---|---|
| 连不上 Python | 502 | `upstream_down` | `python-ai unavailable` |
| 读超时 / 流式超时 | 504 | `upstream_timeout` | `python-ai timeout` |
| Python 4xx | 原样 | `upstream_client_error` 等 | 解析 FastAPI `detail` 字符串或数组 `msg` |
| Python 5xx | 原样（无法解析则 502） | `upstream_down` / `upstream_error` | 截断后的说明，不含堆栈 |

读路径（`lookup` 等）遇到 **5xx** 最多再试 2 次；**504 不重试**，避免把 120s 预算乘 3。写草稿不走读重试。

## 超时预算

| 调用 | 默认 | 配置 |
|---|---|---|
| 建连 | 5s | `regops.python-ai.connect-timeout-ms` |
| 普通读 / `/chat` | 120s | `read-timeout-ms` |
| SSE `/chat/stream` | max(read, 180s) | `stream-timeout-ms` |
| `GET /api/health` 探 Python | **2.5s** | `health-timeout-ms`（不再用 120s 读超时） |

Java 调 Python 的流式客户端固定 **HTTP/1.1**（uvicorn 不接 HTTP/2 前言，否则会变成 `Invalid HTTP request received`）。

## 依赖与降级

```text
/api/health          Java 200 + pythonAi.ok|down     探活 2.5s
/api/chat、/api/tools Python 挂 → 502/504 稳定码
/api/auth、/reviews、/audit  不依赖 Python
```

前端聊天失败展示映射后的短句和关联 ID。系统健康页 Python 卡片在 down 时显示 `error_code`。顶栏降级横幅与四页面体验见 [`W9_UX.md`](./W9_UX.md)。

## 不做什么

- 不改 W6 DAG，不让 Python 写 `REVIEWED`
- Dify 对照见 [`dify-comparison.md`](./dify-comparison.md)，不进本周五条链路

