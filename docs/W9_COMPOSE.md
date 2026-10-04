# W9-4 Docker Compose 一键交付

编排 **web + java-service + python-ai + postgres**。没有绝对路径。密钥从 `.env` 注入，不打进镜像层。

日常开发仍用 `./scripts/dev.sh`（Vite :5173）。Compose 给新环境和演示用。

## 启动

```bash
cp .env.example .env          # 填入 DEEPSEEK_API_KEY；已有 .env 可跳过
docker compose up --build
```

| 服务 | 地址 |
|---|---|
| 前端（nginx） | <http://localhost:8088> |
| Java BFF | <http://localhost:8080/api/health> |
| python-ai | <http://localhost:8000/health> |
| Postgres | localhost:5432 |

首次构建 python-ai 会装 torch / docling，较慢。语料向量缓存在 volume `python_data`。

Java 在 Compose 网络里访问 `http://python-ai:8000`，不要写 `localhost`（那是容器自己）。前端经 nginx 同源反代 `/api/`，SSE 关闭缓冲。

## 冒烟

```bash
./scripts/compose-smoke.sh
```

会等服务健康检查，再跑 `eval/run_w9_e2e.py`（经 Java :8080 验证 RAG 与问数）。

停：`docker compose down`（volume 保留）。清库：`docker compose down -v`。

## 约定

- 相对路径 volume：`./docs/sql/*.sql`、命名卷 `db_data` / `python_data`
- `REGOPS_JWT_SECRET` / `REGOPS_SERVICE_TOKEN` / LLM Key 来自 env
- 健康检查：db `pg_isready`；python `/health`；java `/api/health`；web `/healthz`
- `java-service` 只等 Postgres healthy，**不等 python-ai**。Python 还在构建或被停掉时，Java 探活仍是 200，登录与审计可用（W9-6）
- K8s 最小清单见 [`W9_K8S.md`](./W9_K8S.md)

Compose 用于提供可复现的本地和测试环境；达到规模化部署条件后再引入 K8s，避免无业务需求地增加集群复杂度。
