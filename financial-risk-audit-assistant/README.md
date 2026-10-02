# 金融风险审计助手

这是 RegOps 仓库内的独立 Agent 子项目。基于 DeepAgents 的通用 Harness，默认提供**上市公司公开财报风险线索初筛**。结果用于分析人员核查，不是正式审计意见、授信结论或投资建议。

## 当前能力与边界

- `financial_audit` 为默认业务模式。可调用只读的 RegOps 财务事实与年报证据工具；本模式禁止本机命令执行、文件写入和 Git/Gitee 操作。
- 原有代码分析、开发、方案、代码审查等工程模式保留，仅在用户明确提出相应任务时启用。
- Harness 继续提供工具调用、Skills、运行限额、checkpoint、Store 和 SSE 事件流。
- 未配置 RegOps 服务、财务事实未通过质量门或年报证据不足时，工具返回明确的不可用/缺失结果；系统不得凭模型记忆补造数值。

金融模式现有工具：

| 工具 | 数据来源 | 返回边界 |
| --- | --- | --- |
| `lookup_financial_facts` | RegOps `GET /ops/quality/facts` | 仅将质量门认可、口径与出处完整的事实标为 `ok`；其他状态供人工复核 |
| `search_report_evidence` | RegOps `POST /chat` 的 RAG 链路 | 只保留同公司、同年份且有页码与原文片段的候选证据 |

目前**没有**独立的确定性风险比率计算或正式审计结论模块，不应把检索摘要当作已证实的风险原因。

## 配置

子项目优先读取自己的 `.env`；如果没有，则只从 RegOps 仓库根目录的 `.env` 继承 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `REGOPS_SERVICE_TOKEN`，不会加载数据库等其他凭据。`REGOPS_API_BASE_URL` 默认是本机 `http://127.0.0.1:8000`，需要覆盖时写在子项目 `.env`：

```dotenv
REGOPS_API_BASE_URL=http://127.0.0.1:8000
REGOPS_SERVICE_TOKEN=你的服务令牌
```

`REGOPS_SERVICE_TOKEN` 使用已部署 RegOps 服务自己的服务令牌，不要提交到 Git。工作区、SQLite 和日志默认放在本子项目内，均不纳入 Git。后端与日志目录使用 `FIN_RISK_AUDIT_*` 配置；旧的 `AI_CODING_*` 配置仍兼容。当前工具是 LangChain `@tool` 包装 RegOps HTTP 接口，**尚未迁为 MCP**。

## 启动

macOS/Linux：

```bash
python3.14 -m venv .venv
./.venv/bin/python -m pip install -e .
cd ui && npm ci && cd ..
./.venv/bin/python scripts/sync_skills.py
./.venv/bin/python scripts/start_all.py
```

Windows：分别运行 `scripts\start_backend.cmd`、`scripts\start_ui.cmd`。

- 前端：<http://127.0.0.1:3000/agents>
- 后端健康检查：<http://127.0.0.1:2024/health>

旧目录仍在运行时会占用这两个端口；先停止旧实例再启动子项目。RegOps 的 Python 服务需另行启动在 8000 端口，财务工具才能查询真实数据。

前端使用 Vue 与 POST SSE；后端通过 FastAPI/Uvicorn 运行。对话与 Agent 状态保存在 `data/checkpoints.sqlite`，业务运行记录保存在 `data/store.sqlite`，日志在 `logs/`。服务停启不会清空这些数据。

## 验证

```bash
./.venv/bin/python scripts/verify_financial_audit.py
./.venv/bin/python scripts/verify_backend.py
```

这些本地验证不调用模型或真实财务服务。旧的 Gitee 端到端脚本会创建远程 PR，只能在明确授权的测试仓库运行。
