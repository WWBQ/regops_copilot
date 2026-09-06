# RegOps Copilot

> **基于公开披露数据构建的学习作品集项目，不是任何金融机构的生产系统。**
> 全部业务数据来自上市公司公开年报与监管机构公开文件，不含客户数据或个人隐私信息；
> 模型输出一律附免责声明，不构成合规意见或投资建议。
> 详见 [`docs/DATA_SOURCES.md`](./docs/DATA_SOURCES.md)。

## 解决什么问题

金融机构的合规与投研人员每天要在**上千页的年报和监管制度**里找依据：
某条业务是否触碰监管红线、某个财务数字出自哪一页、结论能不能追溯到具体条款。
翻 PDF 靠人力，而直接问通用大模型会得到**无法追溯、可能编造**的答案——这在合规场景里不可用。

RegOps Copilot 的做法是把「能不能追溯」当作硬约束：

- **答案必须带出处**：RAG 检索年报后作答，每条引用返回 `doc_id` + 页码 + 原文片段 + 可跳转链接，答不出就拒答，不猜。
- **结论必须结构化可校验**：合规结论走 Pydantic DTO（风险等级、条款编号至少一条、置信度），
  高风险结论不允许过高置信度，坏数据在入库前就被拦下。
- **评测必须可复跑**：自建黄金集 + 落盘报告，改了 Prompt 或检索参数后能立刻看出是否变差，
  而不是凭感觉。评测资产见 [`eval/`](./eval)。

## 架构与分工

```
浏览器 → web(:5173) → java-service(:8080) → python-ai(:8000) → Postgres + pgvector
                       BFF/鉴权/审计         LLM/RAG/评测        向量与业务表
```

| 服务 | 技术栈 | 负责 |
|------|--------|------|
| `python-ai` | FastAPI · Python 3.14 | LLM 封装、RAG 检索与引用、文档解析入库、评测任务 |
| `java-service` | Spring Boot · JDK 21 | 对外 API 聚合、认证与 RBAC、maker-checker 复核与审计（W7） |
| `web` | Vue 3 · Vite | 合规问答、文档标注、评测与运维看板 |

服务边界、端点契约、`X-Request-ID` 关联 ID 约定见 [`docs/api-spec.md`](./docs/api-spec.md)。

## 快速启动

首次准备（各一次即可）：

```bash
cp .env.example .env                                        # 填入 DEEPSEEK_API_KEY / QWEN_API_KEY
cd python-ai && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
cd web && npm install && cd ..
```

一键启停四个服务：

```bash
./scripts/dev.sh up          # 启动全部；Docker 未开会自动拉起 Docker Desktop
./scripts/dev.sh status      # 端口 / PID / 健康 + 全链路连通性
./scripts/dev.sh stop        # 停止全部，db 数据保留在 volume db_data
```

| 服务 | 地址 |
| --- | --- |
| 前端 | <http://localhost:5173> |
| Java BFF | <http://localhost:8080/api/health> |
| python-ai Swagger | <http://localhost:8000/docs> |
| Postgres + pgvector | localhost:5432 · regops/regops123 · regops_db |

脚本用法与注意事项见下方[「本地开发脚本」](#本地开发脚本)。

## 试一下

```bash
# 1. 健康检查：应看到 java 与 python-ai 双层状态
curl -s http://localhost:8080/api/health

# 2. 查看已配置可用的模型（只返回配了 Key 的）
curl -s http://localhost:8000/models

# 3. 纯 LLM 对话（不检索）
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"什么是审慎监管？一句话说明","use_rag":false}'

# 4. 年报问答（走 RAG，返回带页码的引用）
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"比亚迪2024年营业收入是多少","use_rag":true}'

# 5. 跑一次合规结论 Schema 校验评测（不依赖 LLM，纯本地）
python-ai/.venv/bin/python eval/run_compliance_schema.py
```

评测报告落在 `eval/reports/<任务>/<时间戳>/`，含 `report.json` 与 `report.md`。
基线与口径说明见 [`docs/eval_w1_baseline.md`](./docs/eval_w1_baseline.md)、
[`docs/eval_rag_retrieval.md`](./docs/eval_rag_retrieval.md)。

## 目录结构

```
regops-copilot/
├── java-service/                         # Java 后端服务 (Spring Boot, JDK21)
│   ├── src/main/java/com/wbq/java_service/
│   │   ├── controller/                   # 控制器层（REST API）
│   │   ├── service/                      # 业务逻辑层
│   │   ├── repository/                   # 数据访问层（JPA）
│   │   ├── entity/                       # 数据库实体类
│   │   ├── dto/                          # 数据传输对象
│   │   ├── config/                       # 配置类（CORS、拦截器等）
│   │   ├── exception/                    # 全局异常处理
│   │   ├── util/                         # 工具类
│   │   └── JavaServiceApplication.java   # Spring Boot 启动类
│   ├── src/main/resources/
│   │   ├── application.yml               # Spring Boot 配置文件
│   │   ├── schema.sql                    # 数据库结构初始化
│   │   └── data.sql                      # 数据库初始数据
│   ├── pom.xml                           # Maven 配置
│   └── Dockerfile                        # Java 服务 Dockerfile
│
├── python-ai/                            # Python AI 服务 (FastAPI + RAG + Agent)
│   ├── app/
│   │   ├── api/                          # FastAPI 路由
│   │   ├── ingest/                       # 文档解析、三表提取、勾稽校验
│   │   ├── rag/                          # 检索、RRF、Rerank、引用、拒答
│   │   ├── text2sql/                     # Schema 检索、SQL 生成、EXPLAIN 校验
│   │   ├── agents/                       # LangGraph 状态图、数字校验节点
│   │   ├── prompts/                      # Prompt 模板库（含版本与变更记录）
│   │   ├── models/                       # 模型封装（LLM、Embedding、Reranker）
│   │   ├── services/                     # AI 服务逻辑
│   │   └── main.py                       # FastAPI 入口
│   ├── requirements.txt                  # Python 依赖
│   └── Dockerfile                        # Python 服务 Dockerfile
│
├── eval/                                  # 评测资产（可复跑、版本固定）
│   ├── golden/                           # 黄金集：RAG 80–100 · 问数 20 · Agent 20 · 安全 25
│   ├── reports/                          # 消融与回归报告（按日期与版本归档）
│   ├── prompt_ab/                        # Prompt A/B 实验脚本与结果
│   └── badcases/                         # 坏例库与层级归因
│
├── web/                                   # 前端 (Vue3 + Vite)
│   ├── src/
│   │   ├── assets/                       # 静态资源
│   │   ├── components/                   # 公共组件
│   │   ├── views/                        # 页面视图
│   │   ├── router/                       # 路由配置
│   │   ├── store/                        # 状态管理（Pinia/Vuex）
│   │   ├── api/                          # 前端 API 封装
│   │   ├── utils/                        # 工具函数
│   │   ├── App.vue                       # 根组件
│   │   └── main.js                       # 前端入口
│   ├── index.html                        # 页面入口
│   ├── package.json                      # 前端依赖
│   ├── vite.config.js                    # Vite 配置
│   └── Dockerfile                        # Vue 前端 Dockerfile
│
├── docs/                                  # 文档目录
│   ├── architecture.md                   # 系统架构设计
│   ├── api-spec.md                       # API 规范（Java + Python）
│   ├── ai-design.md                      # AI 设计（RAG、问数、Agent）
│   ├── DATA_SOURCES.md                   # 公开数据源清单与使用边界声明
│   ├── benchmarks/                       # w1-6 公开基准选型卡（不提交原数据）
│   ├── security.md                       # 安全边界：SQL 只读、PII、注入红队
│   ├── dify-comparison.md                # Dify 对照实现与选型判断
│   └── deployment.md                     # 部署文档（Compose、K8s、信创适配）
│
├── k8s/                                   # 最小 K8s 清单（kind / minikube 可跑）
├── scripts/
│   └── dev.sh                            # 本地一键启停（db + python-ai + java + web）
├── compose.yaml                           # Docker Compose 编排文件
├── .env.example                           # 环境变量示例
└── README.md                              # 项目说明文档
```

## 本地开发脚本

`scripts/dev.sh` 支持 `up / stop / restart / status / logs`：

```bash
./scripts/dev.sh logs java   # 跟踪日志（python | java | web | db）
./scripts/dev.sh restart
./scripts/dev.sh up db python   # 也可只操作部分服务
```

说明：

- 前端 `/api/*` 经 Vite 代理打到 Java BFF，Java 再转发 python-ai，因此三者需同时在线。
- 三个应用进程均为热重载模式（uvicorn `--reload`、Vite HMR、Spring DevTools），改代码无需重启。
- `java-service` 用系统 `mvn` 的离线模式启动（`./mvnw` 需联网下载 Maven 发行包）。若依赖有变动需联网拉取，用 `MVN_OFFLINE=0 ./scripts/dev.sh up java`。
- 表结构由 `compose.yaml` 挂载的 `docs/sql/*.sql` 在容器首次初始化时建立；`ddl-auto: none`，Hibernate 不改表。