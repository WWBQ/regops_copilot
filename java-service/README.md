# java-service

RegOps Copilot 的 Java BFF / 业务网关（Spring Boot 4.1 + Java 21）。

## 职责（与 python-ai 分工）

| 模块 | Owner |
|------|--------|
| LLM / RAG / ingest / 向量 | `python-ai` |
| 认证 RBAC、复核流、审计、BFF 聚合 | `java-service` |

Agent / Python 只写 `PENDING` 草稿。提交和复核只在本服务：`PENDING → SUBMITTED → REVIEWED | REJECTED`。没有 `APPROVED`。详见 [`docs/W7_RBAC.md`](../docs/W7_RBAC.md)。

当前已实现：

- `GET /api/health` — Java + Python 健康检查
- `POST /api/chat` — 转发至 python-ai `/chat`
- `POST /api/chat/stream` — 转发 python-ai SSE，不缓存
- `GET /api/models` — 转发至 python-ai `/models`
- `GET /api/documents/{docId}/viewer-url` — 客户经理访问内核年报返回 404
- `/api/labeling/**` — 转发 python-ai 数据标注
- `X-Request-ID` — 全链路关联 ID
- `/api/tools/**` — 金融工具（部门隔离）；不代理 RAG；`POST /review-draft` 写 PENDING 草稿（不重试）
- Java → Python 带服务身份（`X-Regops-Service` / Token），**不转发用户 JWT**
- `/api/auth/**` — 登录发 JWT
- `/api/reviews/**` — maker-checker
- `/api/customers` — 脱敏客户档案
- `/api/audit/events` — 审计

## 本地启动

先对已有库执行一次 W7 SQL（新 volume 会随 compose 自动跑）：

```bash
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w7_identity.sql
```

```bash
# 1. 数据库
docker compose up -d db

# 2. Python AI（另一个终端）
cd python-ai && uvicorn app.main:app --reload --port 8000

# 3. Java
cd java-service
mvn spring-boot:run

# 4. 前端（可选）
cd web && npm run dev
```

演示账号：`analyst/analyst123`、`checker/checker123`、`rm/rm123`、`admin/admin123`。

```bash
curl -s -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"analyst","password":"analyst123"}'
```

问答和工具 capabilities 仍可不登录。复核 / 客户档案 / 审计必须带 `Authorization: Bearer`。

## 测试

```bash
cd java-service && mvn test
```

工具部门隔离走 H2；W7 企业边界走 `MakerCheckerIT`（Testcontainers 真实 Postgres）。没 Docker 时该 IT 会跳过，不能当过关证据。

## 配置

| 变量 | 默认 |
|------|------|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://localhost:5432/regops_db` |
| `REGOPS_PYTHON_AI_BASE_URL` | `http://localhost:8000` |
| `REGOPS_JWT_SECRET` | 开发默认（至少 32 字符） |

## 目录结构

```
src/main/java/com/wbq/java_service/
├── auth/            # JWT 签发与过滤器
├── identity/        # 用户 / 角色 / 种子
├── review/          # 工单状态机、乐观锁、事务探针
├── audit/           # 审计
├── customer/        # 脱敏客户档案
├── config/          # Security、CORS、RestClient
├── controller/      # BFF REST（含 /api/tools 与 /api/reviews）
├── service/         # 金融工具编排（读走重试；写草稿不重试）
├── tools/           # 部门 ACL、能力树
├── client/          # python-ai HTTP 客户端（服务身份 + 读重试）
├── dto/             # 请求/响应模型
├── filter/          # X-Request-ID
├── util/            # PII 脱敏、读重试
└── exception/       # 统一错误格式（detail 字段，对齐 FastAPI）
```
