# W7 Java 企业边界

> JWT / RBAC / 部门数据域、maker-checker、事务与乐观锁、幂等、审计。证据是 **Testcontainers 真实 Postgres**，不是 H2。

Agent 和 Python **仍然只写 `PENDING` 草稿**。提交、通过、驳回只在 Java。没有 `APPROVED` 这个状态。

## 分工

```text
浏览器 ──JWT──► java-service(:8080)
                 │  登录 / RBAC / 工单状态机 / 审计 / 客户档案
                 │  POST /api/tools/review-draft 仍只代理 Python 写 PENDING
                 ▼
              python-ai(:8000)  LLM / RAG / Agent HITL
                 ▼
              Postgres  同一张 review_draft
```

| 动作 | Owner | 状态 |
|------|--------|------|
| 审查图确认后 `create_review_draft` | Python | `PENDING` |
| 分析师提交 | Java `POST /api/reviews/tickets/{id}/submit` | `SUBMITTED` |
| 合规员通过 / 驳回 | Java `/approve` `/reject` | `REVIEWED` / `REJECTED` |
| 客户经理看内核研报 / 复核 | 禁止 | 工单 403；内核档案/年报 **404** |

## 状态机

`PENDING` → `SUBMITTED` → `REVIEWED` | `REJECTED`

- 终态不能倒流（再 submit → `invalid_state`）
- 复核人 ≠ 提交人（`self_review`）
- 并发复核：`@Version` 乐观锁，只允许一次成功，另一次 409
- 同一 `Idempotency-Key` / `thread_id` 创建只落一行，`replayed=true`

## 身份

演示账号由 Java `DataSeeder` 写入 BCrypt，不把密码哈希写进 SQL。

| 用户 | 角色 | 部门 | 能做 |
|------|------|------|------|
| `analyst` / `analyst123` | ANALYST | research | 建草稿、提交；看本部门工单 |
| `checker` / `checker123` | CHECKER | compliance | 复核别人的单；看全部工单 |
| `rm` / `rm123` | RM | rm | 只看 `CLIENT` 档案（美的/格力）；不能复核、不能看内核 |
| `admin` / `admin123` | ADMIN | compliance | 同 checker |

JWT：HS256（nimbus-jose-jwt），`Authorization: Bearer …`。Claims：`uid` `name` `email` `role` `dept`。

问答 / 评测 / 工具 capabilities **仍然可不登录**。带了 JWT 时，`X-Regops-Dept` 必须和 Token 部门一致。用户 JWT **不转发给 Python**。

## 数据域

| 部门 | 公司 |
|------|------|
| research | 002594 比亚迪、601633 长城 |
| rm | 000333 美的、000651 格力 |
| compliance | 五家金样本 |

客户档案：`INTERNAL_RESEARCH` vs `CLIENT`。客户经理列表里没有内核行；用内核 `public_id` 取值返回 404，不 403。

## API

| 方法 | 路径 | 鉴权 |
|------|------|------|
| POST | `/api/auth/login` | 公开 |
| GET | `/api/auth/me` | JWT |
| GET | `/api/auth/demo-accounts` | 公开 |
| GET/POST | `/api/reviews/tickets` | ANALYST / CHECKER / ADMIN |
| POST | `/api/reviews/tickets/{id}/submit` | 同上 |
| POST | `/api/reviews/tickets/{id}/approve` `/reject` | CHECKER / ADMIN |
| GET | `/api/customers` | 已登录，按角色过滤 |
| GET | `/api/audit/events` | ANALYST / CHECKER / ADMIN |

创建工单可带 `Idempotency-Key`。审计字段：操作人、角色、部门、动作、对象、原因、前后快照、`request_id`。

## 迁移

已有库不会自动跑 `docker-entrypoint-initdb.d` 里后加的脚本：

```bash
psql postgresql://regops:regops123@localhost:5432/regops_db -f docs/sql/w7_identity.sql
```

新库：`compose.yaml` 已挂 `08_w7_identity.sql`。

## 测试

H2 单测覆盖工具部门隔离，**不算** W7 企业边界证据。

```bash
cd java-service && mvn test
```

`MakerCheckerIT` 用 Testcontainers `postgres:16-alpine` 跑：未登录 401、校验 400、幂等创建、客户经理看不到内核/工单/研报 PDF、自审拒绝、分析师提交 + 合规通过、终态不能倒流、并发复核一成功一 409、事务中注入异常后状态和审计一起回滚。

## 前端

`/compliance/review` 建单 / 提交 / 通过 / 驳回。`/compliance/audit` 看留痕。`/settings/users` 登录并看脱敏档案。

## 不做什么

- Python 不把草稿改成 `REVIEWED`
- 没有 `APPROVED` 状态
- 不把 JWT 交给 Python
- 不对全部 `/api/**` 强制登录（现有问答/运维不能先要求账号）
- 不做 W8 Prompt / Dify
