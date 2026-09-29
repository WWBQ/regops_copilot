# W7 身份与数据权限

Java BFF 使用 JWT 认证，按角色和部门限制客户档案与内部年报访问。用户 JWT 不传给 Python；Java 将可信部门信息传给 Python，用于 RAG 检索层的公司范围过滤。

| 演示账号 | 角色 | 部门 | 数据范围 |
|---|---|---|---|
| `analyst/analyst123` | ANALYST | research | 比亚迪、长城汽车等投研资料 |
| `rm/rm123` | RM | rm | 美的、格力等客户资料，不可访问投研内部文档 |
| `admin/admin123` | ADMIN | compliance | 合规部门数据范围 |

已有数据库中的 `CHECKER` 角色为兼容旧账号保留，不再提供审查工单或审批功能。

客户档案分为 `INTERNAL_RESEARCH` 与 `CLIENT`。客户经理列表不返回前者；用其 ID 直接访问也返回 404。文档预览入口执行同类检查。RAG 还在检索层按部门过滤，不依赖提示词约束。

接口：`POST /api/auth/login`、`GET /api/auth/me`、`GET /api/customers`、`GET /api/audit/events`。新库的身份、客户和审计表由 `docs/sql/w7_identity.sql` 初始化；现有数据库不做删除迁移。

验证：

```bash
cd java-service
mvn test
```
