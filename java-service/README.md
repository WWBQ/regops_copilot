# java-service

RegOps Copilot 的 Java BFF / 业务网关（Spring Boot 3 + Java 21）。

## 职责（与 python-ai 分工）

| 模块 | Owner |
|------|--------|
| LLM / RAG / ingest / 向量 | `python-ai` |
| 认证 RBAC、复核流、审计、BFF 聚合 | `java-service` |

当前基座已实现：

- `GET /api/health` — Java + Python 健康检查
- `POST /api/chat` — 转发至 python-ai `/chat`
- `GET /api/models` — 转发至 python-ai `/models`
- `GET /api/documents/{docId}/viewer-url` — 转发文档预签名（W7 加鉴权）
- `/api/labeling/**` — 转发 python-ai 数据标注（任务、模板、导出、PDF/HTML）
- `X-Request-ID` — 全链路关联 ID

## 本地启动

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

验证：

```bash
curl http://localhost:8080/api/health
curl -X POST http://localhost:8080/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"你好"}'
```

## 配置

`application.yaml` 或环境变量：

| 变量 | 默认 |
|------|------|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://localhost:5432/regops_db` |
| `REGOPS_PYTHON_AI_BASE_URL` | `http://localhost:8000` |

## 目录结构

```
src/main/java/com/wbq/java_service/
├── config/          # Security、CORS、RestClient
├── controller/      # BFF REST
├── client/          # python-ai HTTP 客户端
├── dto/             # 请求/响应模型
├── filter/          # X-Request-ID
└── exception/       # 统一错误格式（detail 字段，对齐 FastAPI）
```

## 下一步（W7+）

- JWT 登录 / RBAC
- `dept_acl` 文档权限校验（viewer-url 签发前）
- JPA 实体：用户、复核单、审计日志
- SSE：Java 转发 Python 流式输出
