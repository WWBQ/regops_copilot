# W8-4 Dify 对照（独立编排）

**不要写进根目录 `compose.yaml`。** 根 Compose 是 web / java / python / db。Dify 自带 Postgres、Redis、Weaviate、api、worker、web，混在一起会污染一键启动。

本目录只放端口覆盖和操作说明。官方镜像与数据卷在 `dify/upstream/`（gitignore），不提交。

## 启动

```bash
./scripts/dify-up.sh
```

脚本会浅克隆 [langgenius/dify](https://github.com/langgenius/dify) 的 `docker/`，把 [`.env.overlay`](./.env.overlay) 追加进官方 `.env`，再 `docker compose up -d`。

| 用途 | 地址 |
|---|---|
| 控制台 / 应用 / Service API | <http://localhost:1380> |
| 对照脚本默认 `DIFY_BASE_URL` | `http://localhost:1380/v1` |

首次拉取镜像较慢。Mac mini 16GB 能起，但不要和根 Compose 的 python-ai（torch）同时打满。用完：

```bash
./scripts/dify-down.sh
```

数据在 `dify/upstream/docker/volumes/`，删库加 `-v`（脚本 `--wipe`）。

## 控制台里只搭 3 个应用

导入**同一批**公开年报：`data/raw/*_2024_annual.pdf`（仓库不存 PDF，需本机已下载）。对照范围只包含知识库检索和问答，不额外搭建与当前项目无关的审批流程。

1. **知识库**  
   新建数据集，上传上述 PDF。切分用平台默认即可（对照的是能力边界，不是和 79% Recall 比准确率）。

2. **RAG 聊天应用**  
   Chatbot，挂上该知识库，打开引用。在「访问 API」复制 **App API Key**（`app-…`）。

3. **最小 Workflow**  
   两步：知识库检索 → LLM 汇总。用来感受平台编排上限，不要在里面写库。

模型供应商用和现网相同的 DeepSeek / Qwen（控制台「设置 → 模型供应商」）。Key 只填进 Dify 控制台，不要写进本仓库。

## 对照

把 Key 放进环境（或项目根 `.env`，勿提交）：

```bash
export DIFY_BASE_URL=http://localhost:1380/v1
export DIFY_APP_KEY=app-xxxxxxxx
# 本仓库 /chat，默认 http://127.0.0.1:8000
export REGOPS_CHAT_URL=http://127.0.0.1:8000/chat
```

```bash
python-ai/.venv/bin/python eval/run_w8_dify_compare.py
```

Dify 没起来或没配 Key：**跳过**，退出码 0，pytest 同样不绑死 CI。有容器时原始 JSON 写到 `eval/dify/runs/`（gitignore）。口径与 q67 见 [`docs/dify-comparison.md`](../docs/dify-comparison.md)。

HiAgent / 扣子只口头对照，不再部署一套。
