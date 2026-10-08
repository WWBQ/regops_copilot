# W7 身份与数据权限

Java BFF 使用 JWT 认证，按角色和部门限制年报访问。用户 JWT 不传给 Python；Java 将可信部门信息传给 Python，用于 RAG 检索层的公司范围过滤。

| 演示账号 | 角色 | 部门 | 数据范围 |
|---|---|---|---|
| `analyst/analyst123` | ANALYST | research | 比亚迪、长城汽车等投研资料 |
| `rm/rm123` | RM | rm | 美的、格力等客户资料，不可访问投研内部文档 |
| `admin/admin123` | ADMIN | compliance | 合规部门数据范围 |

已有数据库中的 `CHECKER` 角色为兼容旧账号保留，不再提供审查工单或审批功能。

年报文档按部门公司白名单授权。文档预览入口执行同类检查；RAG 还在检索层按部门过滤，不依赖提示词约束。

接口：`POST /api/auth/login`、`GET /api/auth/me`。新库的身份表由 `docs/sql/w7_identity.sql` 初始化。历史库中的 `audit_event` 与 `customer_profile` 表不会自动删除，避免误删既有数据；当前应用不再读写它们。

验证：

```bash
cd java-service
mvn test
```
