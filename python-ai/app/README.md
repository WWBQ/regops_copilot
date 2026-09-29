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

## 阅读顺序

建议按一条真实请求学习：

1. `chat/router.py`：请求如何进入系统、如何选择问数或 RAG。
2. `asknum/lookup.py`：结构化财务数字为什么不交给模型猜。
3. `rag/service.py`：检索、融合、精排和引用如何产生。
4. `models/llm.py`：LangChain 如何调用具体模型并统计 Token/延迟。
5. `db/`：最后再看事实表、文档块和 Trace 如何落库。

目录约定：`router.py` 只处理 HTTP；`schemas.py` 只定义请求/响应；业务逻辑放在 `service.py`、`pipeline.py` 或语义明确的文件中；SQL 访问集中在 `db/`。
