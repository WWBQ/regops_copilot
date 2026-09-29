# W9-6 SSE 与依赖降级

前端保留聊天、RAG 引用、问数结果与运维监控。聊天使用 `POST /api/chat/stream`，事件为 `status`、`meta`、`delta`、`done`、`error`。生成中可用 `AbortController` 停止请求。

| 页面 | 路由 | 依赖 |
|---|---|---|
| 合规问答（含 RAG、问数） | `/` | Java → Python |
| 问数监控 | `/ops/asknum` | Java → Python |
| 审计追踪 | `/compliance/audit` | Java + PostgreSQL |

`GET /api/health` 在 Python 不可用时仍返回 Java 自身状态，并在响应体标识 `pythonAi.status=down`。前端据此显示降级横幅：Python 挂时聊天/问数不可用，登录、客户档案和审计仍可用；Java 挂时 BFF 相关页面不可用。

SSE 适合单向逐段输出；若需要双向实时协作才考虑 WebSocket。
