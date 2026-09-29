# W9-1 双栈贯通与降级

调用链：浏览器 → Java BFF → Python AI 服务 → PostgreSQL/pgvector 与模型 API。聊天、RAG 和问数共用 `/api/chat`；流式响应使用 `/api/chat/stream`。

| 链路 | 入口 | 预期 |
|---|---|---|
| 健康检查 | `GET /api/health` | Java 自身可用时返回 200，响应体单独标识 Python 状态 |
| RAG | `POST /api/chat` | 检索年报、附引用；无证据数字会被拦截 |
| 问数 | `POST /api/chat` | 只返回已核验的财务事实，缺失或待复核时拒绝给数 |

`X-Request-ID` 在浏览器、Java、Python 间传递并回写响应。Java 不转发用户 JWT，仅传服务身份和可信部门。Python 不可用时聊天/问数返回 `502 upstream_down` 或 `504 upstream_timeout`；登录、客户档案与审计仍由 Java 提供。

默认预算：建连 5 秒、普通读取 120 秒、SSE 最少 180 秒、健康探针 2.5 秒。Java 的 SSE 使用异步派发，安全配置需允许该派发阶段。

运行双栈冒烟：

```bash
python-ai/.venv/bin/python eval/run_w9_e2e.py
```

脚本检查健康、RAG 与问数，并将报告写入 `eval/reports/w9_e2e/`。

