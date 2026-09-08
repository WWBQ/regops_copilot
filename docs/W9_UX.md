# W9-6 SSE、四页面与无 AI 降级

> 把已有后端能力收成可演示产品：聊天引用、问数结果、工单复核、审计。不展示思维链。错误是人话。**python-ai 挂了时 Java 业务仍可用。**

## 四页面

| 页面 | 路由 | 依赖 |
|---|---|---|
| 合规问答（引用 + 问数 chip） | `/` | Java → Python SSE |
| 问数监控（命中 / 拦截 / 反问） | `/ops/asknum` | Java → Python 读 trace |
| 合规复核 | `/compliance/review` | **只打 Java** |
| 审计追踪 | `/compliance/audit` | **只打 Java** |

问数没有单独「结果页」：首页问「营收是多少」走 `route=metric*`，引用气泡可点；`/ops/asknum` 是同一批真实提问的监控。

## SSE 与取消

`POST /api/chat/stream`，`Accept: text/event-stream`。事件只有 `status` / `meta` / `delta` / `done` / `error`。nginx 与 Java 都关缓冲。

生成中输入栏按钮是 **停止**，`AbortController.abort()` 取消 fetch。不要把思维链（Thought / Action / Observation）画到气泡里；`status` 只保留「正在检索…」这类进度。

为什么不用 WebSocket：问答是服务端单向推 token，SSE 足够，能走现有 HTTP 鉴权与反代。要房间、双向信令再上 WS。课程口试见「课程 q37：SSE 与 WebSocket」（与仓库 Q37 Text2SQL 题号撞车，不是同一题）。

## 健康拆分

`GET /api/health` 在 Python 挂了时仍是 Java **200**，`pythonAi.status=down`。前端不再用 `getModels()` 判断整站死活。

| Java | Python | 行为 |
|---|---|---|
| 通 | 通 | 正常问答 |
| 通 | 挂 | 顶栏黄条：问答 / 问数暂不可用，链到复核和审计 |
| 挂 | — | 顶栏红条：BFF 不可用 |

轮询约 20 秒。聊天 502 只把 `pythonOk` 打成 false，不把 Java 标死。

Compose 里 `java-service` 只等 Postgres healthy，**不等 python-ai**，便于本地 `docker compose stop python-ai` 演示同一条故事。K8s：`kubectl -n regops scale deploy/python-ai --replicas=0`。

## 不做什么

- 不改 W6 DAG，不让 Python 写 `REVIEWED`
- 不把 CoT / tool_trace 渲染到聊天
- 不做 W8-4 Dify
