# Python AI 代码地图

本目录采用“按业务功能集中”的结构。读一个功能时，从该目录的 `router.py` 开始，再看同目录的 `schemas.py` 和业务文件，不需要在统一的 `api/`、`schemas/` 目录之间来回跳。

## 启动链路

```text
main.py
  → router.py（全部 HTTP 路由清单）
  → 各功能/router.py
  → 各功能的 service / pipeline / repository
```

## 功能模块

| 目录 | 负责什么 | 建议入口 |
|---|---|---|
| `chat/` | 统一聊天入口，路由到普通对话、RAG 或问数 | `router.py` |
| `models/` | LangChain 模型调用、模型选择、Token 与延迟 | `llm.py` |
| `rag/` | 向量与关键词召回、RRF、精排、引用、数字校验 | `service.py` |
| `mcp/` | 对 Agent 提供金融事实和年报证据的只读 MCP 服务端 | `financial_server.py` |
| `asknum/` | 公司/科目/年份解析，查询财务事实库，拒绝不可靠数字 | `lookup.py` |
| `documents/` | 文档上传、元数据、预签名查看地址 | `router.py` → `service.py` |
| `ingest/` | PDF 解析、清洗、切分、Embedding、财务数据校验与入库 | `pipeline.py` |
| `sessions/` | 聊天会话和会话级 PDF | `router.py` |
| `labeling/` | 数据标注任务、标注项和结果保存 | `router.py` → `store.py` |
| `quality/` | 财务事实质量门和质量看板 | `router.py` → `service.py` |
| `eval/` | 黄金集、评测任务、指标和报告 | `router.py` → `job_service.py` |
| `prompts/` | Prompt 模板、版本钉扎和回滚 | `library.py` |
| `ops/` | RAG/问数 Trace、日志、入库和系统监控 | `router.py` |
| `obs/` | LLM Token、延迟、成本和 Langfuse 可观测性 | `generations.py` |

## 公共基础设施

| 目录/文件 | 负责什么 |
|---|---|
| `core/` | FastAPI 公共依赖和健康检查 |
| `db/` | PostgreSQL 连接与各表 Repository |
| `storage/` | 本地对象存储和预签名访问 |
| `security/` | Java → Python 服务身份校验 |
| `config.py` | 环境变量与全局配置 |
| `logging_config.py` / `request_id.py` | 日志、Request ID 与 Trace 上下文 |

## 金融 MCP 服务端

金融工具放在本项目的 `app/mcp/`；`app/rag/` 只负责检索算法。现有 FastAPI 在受服务令牌保护的 `/mcp/` 挂载 FastMCP HTTP 服务，Agent 项目的 `agent/mcp/` 作为客户端只发现两项白名单工具。服务不可达或工具不完整时，风险初筛页面仍返回 503。

普通启动已从 `requirements.txt` 安装 FastMCP，无需另外启动进程。可选的 stdio 独立验证环境：进入 `python-ai` 目录后运行：

```bash
python3.14 -m venv .venv-mcp
./.venv-mcp/bin/python -m pip install -r requirements-mcp.txt
./.venv-mcp/bin/python scripts/verify_financial_mcp.py
./.venv-mcp/bin/python -m app.mcp.financial_server
```

最后一条命令是可选的 stdio 服务，不用于 RegOps 页面。页面实际使用 `http://127.0.0.1:8000/mcp/`（Compose 内为 `http://python-ai:8000/mcp/`）。`lookup_financial_facts` 通过 `REGOPS_API_BASE_URL` 读取 F10 网页结构化事实：只接受质量门 `auto_accepted` 或已完成数据审核的 `manually_accepted`、合并报表、人民币、完整 SHA-256 来源哈希；返回中明确标注 `source_type=web` 和 `content_hash`，不伪造 PDF 页码。哈希在入库时由原始 F10 文件包计算，查询时只校验已存哈希格式与质量门状态，不重新读取原始文件。`search_report_evidence` 则在本服务内按公司、年份和入库状态锁定 PDF 年报，再直接复用 RAG 检索，返回带页码的候选片段，不经过 `/chat` 或回答模型。配置为本地 BGE 时可执行重排；配置为 LLM 重排时退回 Hybrid 检索，避免工具额外调用聊天模型。候选片段仍需核对年报原文。

## PDF 解析器切换

默认用 Docling；MinerU 4.x 是可选的高精度解析模块。两者都会转换为统一的
`PageBlock / TableBlock`，所以清洗、切块、Embedding 和 RAG 不需要分两套实现。

```bash
# 只有要用 MinerU 时才安装（默认 requirements.txt 不强制安装大型依赖）
cd python-ai
.venv/bin/pip install -r requirements-mineru.txt

# 全局切换：写入项目根目录 .env
DOCUMENT_PARSER_BACKEND=mineru
MINERU_TIER=standard
MINERU_OCR_MODE=auto

# 单次批量入库覆盖全局配置
.venv/bin/python scripts/ingest_pdf_to_vectors.py --parser mineru --no-parse-cache ../data/raw/demo.pdf
```

`POST /ingest` 也提供 `parser_backend=docling|mineru` 表单字段。两种解析器的
parse artifact 缓存路径相互隔离，chunk 元数据会记录 `parser_backend`。MinerU
未安装或解析失败时会让 ingest 明确失败，不会静默回退到 Docling，避免掩盖数据质量问题。

## RAG 重排器切换

默认使用本地 BGE Cross-Encoder。也可以把候选片段交给 OpenAI 兼容的本地
Ollama/vLLM 或远程模型 API 做结构化相关性判断：

```bash
# BGE（默认）
RAG_RERANK_ENABLED=true
RAG_RERANK_BACKEND=bge

# 本地 LLM
RAG_RERANK_BACKEND=llm
RAG_LLM_RERANK_DEPLOYMENT=local
RAG_LLM_RERANK_MODEL=qwen3:8b
RAG_LLM_RERANK_BASE_URL=http://127.0.0.1:11434/v1
RAG_LLM_RERANK_API_KEY=local

# 远程 API：填写供应商的 OpenAI 兼容地址、模型 ID 和独立 Key
RAG_LLM_RERANK_DEPLOYMENT=api
```

Python 服务直接在宿主机运行时，本地地址可写 `127.0.0.1`；如果 Python 服务运行在
Compose 容器内，macOS/Windows 应改用 `host.docker.internal`，或使用同一 Compose
网络中的模型服务名。

LLM 重排只接收 RRF 后的少量候选，默认 12 条、每条最多 800 字。返回结果用
Pydantic 校验，模型输出的 0～100 分不会和向量/RRF 分数混算。调用或结构校验失败时
会明确记录 trace 并回退到 BGE；模型明确判断“没有直接证据”时不会回退。

`GET /ops/system/overview` 检查 Python、PostgreSQL、pgvector、Redis 和 RabbitMQ；
Redis 返回内存与连接数，RabbitMQ 只读查询 `ingest` 队列的待消费消息与消费者数。
面向页面的 `/api/ops/system/overview` 由 Java BFF 汇总入口请求、JVM 压力和依赖状态。
RAG 后端、耗时、排序与降级情况在 `/ops/rag-traces` 查看。

## 暂缓：模型问题改写

后续可以增加一次结构化 Query Planner：由 LLM 把“某公司某年经营得怎么样”改写成
受约束的查询计划，再由程序执行事实库与 RAG。当前暂不实现，仍使用确定性意图规则；
未来实现时必须保留原问题，并校验公司、年份和指标白名单，不能无条件执行模型生成的
自然语言查询。

## RAG 配置寻优

2026-10-01 已用校验通过的 100 题黄金集完成候选数扫描。40 / 80 条在冒烟中已出现
33～76 秒的单题延迟且质量没有改善，正式分层样本继续比较 12 / 24：两套场景 Recall
相同，12 条的 MRR / nDCG / 引用准确率更好，P95 约为 24 条的 1/3～1/4。

当前固定：`rag_rerank_candidates=12`、`rag_compare_rerank_candidates=12`。完整数据和
复跑命令见 `docs/eval_rag_tuning.md`；后续若更换语料、Embedding 或重排模型必须重新跑，
不能把本机样本结论永久写死。

统一请求性能可通过 `GET /ops/performance-traces` 和
`GET /ops/performance/overview` 查看。它把 AskNum、RAG、重排、回答模型、校验、
流式首 Token 和端到端总耗时关联到同一个 Request ID；标准日志也会输出
`performance_trace` JSON，但不会记录问题正文或文档片段。

## 阅读顺序

建议按一条真实请求追踪调用链：

1. `chat/router.py`：请求如何进入系统、如何选择问数或 RAG。
2. `asknum/lookup.py`：结构化财务数字为什么不交给模型猜。
3. `rag/service.py`：检索、融合、精排和引用如何产生。
4. `models/llm.py`：LangChain 如何调用具体模型并统计 Token/延迟。
5. `db/`：最后再看事实表、文档块和 Trace 如何落库。

目录约定：`router.py` 只处理 HTTP；`schemas.py` 只定义请求/响应；业务逻辑放在 `service.py`、`pipeline.py` 或语义明确的文件中；SQL 访问集中在 `db/`。
