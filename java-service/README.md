# java-service

Spring Boot BFF，负责前端 API 聚合、登录认证、部门权限、文档预览权限与审计。LLM、RAG、问数、文档解析和评测由 `python-ai` 提供。

## 主要接口

- `GET /api/health`：Java 与 Python 状态。
- `GET /api/models`、`POST /api/chat`、`POST /api/chat/stream`：代理模型聊天、RAG 和问数，流式响应保持 SSE。
- `/api/sessions/**`、`/api/documents/**`、`/api/labeling/**`：会话、文档与数据标注。
- `/api/ops/**`：检索、问数、入库、质量和评测监控。
- `/api/auth/**`：JWT 登录；`GET /api/audit/events`：审计。

Java 向 Python 透传 `X-Request-ID` 和部门信息，不转发用户 JWT。不同部门只能访问授权公司的年报数据域。

## 本地运行

先启动数据库和 `python-ai`，再运行：

```bash
cd java-service
mvn spring-boot:run
```

已有数据库如缺少身份表，可运行 `docs/sql/w7_identity.sql`；新数据库由 Compose 初始化。演示账号：`analyst/analyst123`、`rm/rm123`、`admin/admin123`。

## 测试

```bash
cd java-service
mvn test
```

超时与错误映射见 [W9_E2E.md](../docs/W9_E2E.md)，部门权限见 [W7_RBAC.md](../docs/W7_RBAC.md)。
