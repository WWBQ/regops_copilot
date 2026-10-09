# 金融风险审计助手

金融风险审计助手是 RegOps Copilot 的 Agent 服务，面向上市公司公开财报执行**风险线索初筛**。它帮助分析人员更快找到值得核查的指标、原文和证据缺口，不出具正式审计意见、授信结论或投资建议。

前端已集成到 RegOps：风险初筛在 <http://localhost:5173/risk-agent>，AI Coding 在 <http://localhost:5173/ai-coding>（仅管理员）。本目录不再维护独立 Web UI，也不需要安装成 Python package，直接从源码启动 `agent.app:app`。

两个产品运行在同一 FastAPI 进程，但使用独立的 `/regops/agent`、`/regops/coding-agent` 路由和互不重叠的会话 ID。风险初筛强制只读金融模式；AI Coding 使用 DeepAgents 工作区模式，不装配金融 MCP 工具。两者只共用模型配置、运行记录、事件流与 PostgreSQL 持久化基础设施。AI Coding 默认仍是本机执行，仅管理员可访问；可显式切换到 OpenSandbox 隔离模式。

## 已实现能力

- 在页面选择具体 DeepSeek 或 Qwen 模型，而不是只选择供应商。
- Agent 在调用预算内自主决定查询哪些财务指标、检索哪些年报叙述。
- 通过 FastMCP 只访问 `lookup_financial_facts`、`search_report_evidence` 两个金融只读工具。
- Agent 内部提供 `search_external_risk_signals`，用于搜索监管、问询、诉讼、违约等外部公开线索。
- F10 财务事实使用质量门状态和 SHA-256 来源校验；PDF 年报证据必须包含真实页码。
- 工具证据统一分配 `citation_id`，回答中的 `[1]`、`[2]` 可以跳转到事实库或年报原页。
- 同一次模型输出同时生成用户可读 Markdown 和机器可读 `RiskAuditResult`。
- Pydantic 校验结构、状态、严重程度和必填字段，并拒绝不存在的证据编号。
- `RiskFinding` 保存严重程度、结论、数据点、不确定性、人工核查问题和审核状态。
- POST SSE 实时返回执行阶段和最终回答；checkpoint 支持多轮会话及刷新恢复。
- 会话按 RegOps 登录用户隔离，MCP 不可用时在执行前失败关闭。

## 业务边界

金融模式不允许：

- 执行本机命令、修改文件或操作 Git/Gitee。
- 直接访问数据库或绕过 MCP 工具合同。
- 使用模型记忆、网页摘要或未验证数据补造财务数值。
- 把普通网页线索直接表述为财务造假、违规或因果关系认定。
- 把 `missing`、`unverified`、`conflict`、`missing_provenance`、`insufficient_evidence`、`unavailable` 当成可靠事实。
- 将候选原文直接表述为审计认定。

通用 DeepAgents Harness 的编程、审查和 Skills 能力通过独立的 AI Coding 页面提供；`/risk-agent` 接口强制进入 `financial_audit`，不会装配代码工具。反过来，AI Coding API 也不会进入金融风险 Agent 模式。

## 架构

```mermaid
flowchart LR
    WEB[RegOps Vue<br/>/risk-agent] -->|POST SSE| JAVA[Java BFF<br/>/api/risk-agent]
    CODING_WEB[RegOps Vue<br/>/ai-coding] -->|管理员 POST SSE| CODING_JAVA[Java BFF<br/>/api/coding-agent]
    JAVA -->|用户 UUID + 服务令牌| API[Agent FastAPI<br/>:2024]
    CODING_JAVA --> API
    API --> RUNTIME[runtime.py<br/>会话与运行编排]
    RUNTIME --> GRAPH[金融 LangChain Agent<br/>模型 + 调用限额]
    RUNTIME --> CODING_GRAPH[AI Coding DeepAgents<br/>工作区 + Skills]
    GRAPH --> CLIENT[MCP Client<br/>工具白名单]
    GRAPH --> WEBSEARCH[Agent 内部 Web Search<br/>外部风险线索]
    CLIENT -->|Streamable HTTP| MCP[python-ai /mcp/]
    MCP --> FACTS[财务事实质量门]
    MCP --> RAG[指定 PDF 年报检索]
    GRAPH --> RESULT[引用编号 + RiskAuditResult]
    RUNTIME --> CP[(PostgreSQL<br/>LangGraph checkpoint)]
    CODING_GRAPH --> CP
    RESULT --> STORE[(PostgreSQL agent schema<br/>业务 Store)]
    RESULT --> API
```

完整系统图和请求时序见 [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)。

## 一次请求如何执行

1. Vue 把问题和 `model_id` 发送到 Java BFF。
2. Java 从登录上下文提取用户 UUID，将 POST SSE 转发到 Agent。
3. Agent 在创建或继续会话前发现 MCP 工具；缺少任一白名单工具就返回 `503`。
4. `runtime.py` 创建 run，`server.py` 按任务类型转到 `financial/factory.py`，由后者装配模型、两个 MCP 工具、一个内部 Web Search 工具、checkpoint 和调用限额。
5. 模型自主调用工具；`ToolCitationIndexer` 给真实工具证据分配连续编号。
6. 模型输出 Markdown 和末尾的 `risk_audit_result` JSON。
7. `risk_result.py` 使用 Pydantic 校验 JSON，并确认每个 `evidence_id` 都来自本轮工具结果。
8. checkpoint 保存完整对话；业务 Store 保存 run、结构化结果和 findings。
9. API 通过 SSE 返回干净 Markdown、引用和结构化结果；机器 JSON 不展示给用户。

## 目录

```text
financial-risk-audit-assistant/
├── agent/
│   ├── app.py                         FastAPI 入口
│   ├── api/
│   │   ├── health.py                  健康检查
│   │   ├── risk_agent.py              金融会话、历史、POST SSE
│   │   ├── coding_agent.py            AI Coding 会话、历史、POST SSE
│   │   └── auth.py                    RegOps 服务令牌与用户身份校验
│   ├── coding/service.py              DeepAgents 工作区任务入口
│   ├── coding/factory.py              AI Coding 图、工作区和 Skills 装配
│   ├── financial/service.py           只读风险初筛任务入口
│   ├── financial/factory.py           金融工具和只读 Agent 图装配
│   ├── mcp/financial_client.py         MCP 工具发现、白名单和同步适配
│   ├── tools/external_risk_search.py   Agent 内部外部风险线索搜索
│   ├── tools/web_search_providers.py   SearXNG / 智谱 / Brave 适配层
│   ├── financial/
│   │   ├── citations.py               citation_id 分配与前端 Citation
│   │   └── risk_result.py              RiskFinding / RiskAuditResult 契约
│   ├── core/
│   │   ├── runtime.py                 任务、run、最终结果编排
│   │   ├── streaming_runtime.py       LangGraph V3 事件流适配
│   │   ├── checkpoint_history.py      历史恢复与机器 JSON 隐藏
│   │   ├── graph.py · persistence.py  PostgreSQL checkpoint / Store
│   │   └── model.py                   模型目录与 LangChain 初始化
│   ├── store/postgres_store.py        运行记录和结构化风险结果
│   ├── store/sqlite_store.py          旧数据迁移及本地测试兼容
│   ├── prompt.py                      金融边界与结构化输出规则
│   ├── server.py                      按任务类型分派两个图工厂
│   └── skills/                        金融初筛及保留的工程 Skills
├── data/                               旧 SQLite 数据；迁移后不再写入
├── logs/                               Agent 日志，Git 忽略
├── scripts/                            启动、同步 Skills 和验证脚本
├── requirements.txt
└── Dockerfile
```

## 数据存储

| PostgreSQL 表 | 内容 |
| --- | --- |
| LangGraph `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` | messages、工具调用和图状态；历史正文的权威来源 |
| `agent.threads`、`agent.runs` | 会话摘要和每次运行状态 |
| `agent.risk_audit_results` | 公司、年份、状态、摘要、证据缺口和报告哈希 |
| `agent.risk_audit_findings` | 逐条风险线索及 `pending_review` 状态 |
| LangGraph `store` | 通用 Harness 的 StoreBackend；金融事实不从这里读取 |

刷新页面时，聊天正文从 checkpoint 恢复，结构化结果按回答哈希关联回对应消息。删除会话时同步清理业务 Store 和 checkpoint。旧 SQLite 保留为迁移备份，可用 `PYTHONPATH=. .venv/bin/python scripts/migrate_sqlite_to_postgres.py` 重跑幂等导入。

## 配置

服务优先读取 RegOps 根目录 `.env`，子项目 `.env` 可覆盖。至少需要：

```dotenv
REGOPS_SERVICE_TOKEN=change-me
REGOPS_MCP_URL=http://127.0.0.1:8000/mcp/
DEEPSEEK_API_KEY=
QWEN_API_KEY=
FIN_RISK_WEB_SEARCH_PROVIDER=searxng
FIN_RISK_WEB_FALLBACK_PROVIDERS=zhipu,brave
SEARXNG_BASE_URL=http://127.0.0.1:8888
ZHIPU_API_KEY=
BRAVE_SEARCH_API_KEY=
FIN_RISK_WEB_ALLOWED_DOMAINS=csrc.gov.cn,sse.com.cn,szse.cn,cninfo.com.cn,bse.cn,samr.gov.cn,court.gov.cn,wenshu.court.gov.cn,zxgk.court.gov.cn,xinhua.com,people.com.cn,stcn.com,cs.com.cn,cnstock.com,yicai.com,caixin.com
FIN_RISK_WEB_TIMEOUT_SECONDS=10
FIN_RISK_WEB_CACHE_TTL_SECONDS=600
FIN_RISK_WEB_MAX_CALLS_PER_RUN=2
AGENT_FINANCIAL_AUDIT_MAX_TOOL_CALLS=20
AGENT_FINANCIAL_AUDIT_MAX_SECONDS=300
MAIN_MODEL=deepseek-v4-pro
AGENT_DATABASE_URL=postgresql://regops:password@localhost:5432/regops_db
```

- `REGOPS_SERVICE_TOKEN` 必须与 Java BFF、`python-ai` 一致，不能提交到 Git。
- 外部搜索默认使用本地 SearXNG；`FIN_RISK_WEB_SEARCH_PROVIDER` 可切换为 `zhipu` 或 `brave`，`FIN_RISK_WEB_FALLBACK_PROVIDERS` 定义失败后的备用顺序。
- SearXNG 不需要第三方 API Key；使用智谱或 Brave 时分别配置 `ZHIPU_API_KEY`、`BRAVE_SEARCH_API_KEY`。所有后端均不可用时只返回 `unavailable`，不阻断财务事实和年报初筛。
- 每次搜索先执行证监会、交易所、巨潮资讯等官方域名限定查询，不足时再补通用检索；最终仍只保留白名单结果并把官方来源排在前面。单次最多 5 条、单轮默认最多调用 2 次，结果在进程内缓存 10 分钟。
- `AGENT_FINANCIAL_AUDIT_MAX_TOOL_CALLS` 是整轮 Agent 的工具总预算，默认 20 次；财务事实、年报证据和外部搜索都计入。该值同时用于 Agent 图和运行保护，避免两套阈值互相冲突。
- Compose 中 MCP 地址使用 `http://python-ai:8000/mcp/`。
- 模型列表只返回已经配置对应 API Key 的具体型号。
- `AGENT_DATABASE_URL` 默认继承根目录 `DATABASE_URL`；Compose 会覆盖为容器内 `db:5432`。三个旧 SQLite 路径只供迁移脚本读取。

### AI Coding 的 OpenSandbox 模式

在根目录 `.env` 或子项目 `.env` 配置 `AI_CODING_EXECUTION_BACKEND=opensandbox`，并填写 `AI_CODING_SANDBOX_DOMAIN`（`host:port`）、`AI_CODING_SANDBOX_API_KEY`。可选 `AI_CODING_SANDBOX_PROTOCOL=https`、`AI_CODING_SANDBOX_IMAGE=opensandbox/code-interpreter:v1.1.0`。本机启动与 Compose 部署时，`DOMAIN` 必须分别是 Agent 进程可达的地址；不要在容器内填宿主机的 `localhost`。

本地沙箱服务使用独立的 kind + Kubernetes 集群，部署步骤见 [`deploy/opensandbox/README.md`](../deploy/opensandbox/README.md)。OpenSandbox 生命周期服务通过 Kubernetes API 创建 Pod，不挂载宿主机 Docker socket。API 和网关分别通过仅绑定 `127.0.0.1` 的端口转发提供给本机 Agent。先验证鉴权、创建沙箱、命令执行和实际断网，再把执行模式切为 `opensandbox`。

沙箱由独立的 OpenSandbox 服务创建，60 分钟自动过期，限制 1 CPU/2 GiB，请求默认拒绝外网。kind 部署启用 OpenSandbox egress sidecar；仅在 SDK 中传 `deny` 而未实测断网，不可视为完成网络隔离。kind 是本地学习环境，不能等同于生产级多租户安全边界；生产环境还需强化节点隔离、镜像准入、资源配额、网络策略和审计。

用户在 AI Coding 页面选择项目后，首次运行会把 `workspace/projects/<项目名>` 的受限文件快照和三项 AI Coding Skills 复制到沙箱；跳过常见隐藏凭据、`.git`、虚拟环境、依赖目录和符号链接，超过 2000 文件或 20 MiB 则拒绝。不会挂载宿主目录，也不会主动注入模型 Key 或 Gitee Token；但普通源码文件也可能含敏感信息，选择项目之前仍需检查。沙箱 ID 写入 `agent.threads`，后续轮次和服务重启后尝试连接同一实例并续期 60 分钟；实例过期或连接失败会报错，不新建空沙箱、不回退本机。删除会话时销毁对应沙箱。当前仅有进程内创建锁，多实例部署前还需加数据库级会话锁，避免同一会话并发创建多个容器。

沙箱模式提供容器内读写与命令执行，任务结束后可在 AI Coding 页面导出所选项目的 ZIP 快照；下载内容再次排除隐藏文件、凭据和符号链接，并限制为 2000 文件 / 20 MiB。不装配本机 Gitee、Web Search 或 Reviewer 工具，也不自动把 ZIP 合并回宿主项目。下载后需人工检查与合并；不要把沙箱里的“修改完成”等同于宿主项目已经修改。

完整示例见根目录 [`.env.example`](../.env.example)。

## 启动

推荐从 RegOps 根目录统一启动：

```bash
./scripts/dev.sh up
./scripts/dev.sh status
```

只启动 Agent：

```bash
cd financial-risk-audit-assistant
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python scripts/sync_skills.py
cd ..
./scripts/dev.sh up agent
```

修改 Agent Python 代码后执行：

```bash
./scripts/dev.sh restart agent
```

健康检查：<http://127.0.0.1:2024/health>。真实金融工具还要求 `python-ai` 在 `:8000` 运行并已准备 PostgreSQL 数据。

## 验证

以下命令不调用真实模型：

```bash
financial-risk-audit-assistant/.venv/bin/python financial-risk-audit-assistant/scripts/verify_risk_audit_result.py
financial-risk-audit-assistant/.venv/bin/python financial-risk-audit-assistant/scripts/verify_risk_agent_messages.py
financial-risk-audit-assistant/.venv/bin/python financial-risk-audit-assistant/scripts/verify_financial_audit.py
financial-risk-audit-assistant/.venv/bin/python financial-risk-audit-assistant/scripts/verify_backend.py
cd web && npm test && npm run build
```

## 当前下一步

1. 建立 20～30 条金融风险黄金评测集。
2. 增加结构化 finding 的人工接受、驳回和修改接口及页面。
3. 对比不同模型的召回率、误报率、引用正确率、耗时和成本。
