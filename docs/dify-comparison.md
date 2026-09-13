# W8-4 Dify 对照（选型，不替换现网）

> 平台负责快，代码负责能测、能拦、能审计。金融里更贵的是「能跑但口径错」，所以主路径不交给 Dify。
>
> **不替换** `/chat`、W6 DAG、Java 工单。HiAgent / 扣子只口头当同类，不再部署。

## 怎么复现

```bash
./scripts/dify-up.sh          # 独立编排，控制台 http://localhost:1380
# 控制台：配模型 → 知识库导入 data/raw/*_2024_annual.pdf → 建 RAG Chatbot
export DIFY_APP_KEY=app-...
python-ai/.venv/bin/python eval/run_w8_dify_compare.py --write-example
```

Dify 没起来或没配 Key：脚本和 pytest **跳过**，退出码 0，不绑 CI。步骤见 [`dify/README.md`](../dify/README.md)。黄金集：[`eval/golden/w8_dify_12.json`](../eval/golden/w8_dify_12.json)（12 题：问数、年报叙述、库外拒答、注入、经营概况、两家+结论）。

对照的是**能力边界**，不要把 Dify 默认切分和本仓库 RRF + rerank 的页级 Recall 报成同一张准确率表。

## 选型表

| 维度 | Dify | 本仓库 |
|---|---|---|
| 编排 | 画布拖节点，改流程不发版 | 问数 / RAG / 审查图 / 门禁后的工具循环，写在代码里 |
| 知识库 | 平台切分 + 向量库（Weaviate） | Docling → chunk → pgvector + Okapi BM25 + RRF + rerank |
| 出处 | 片段引用，页码取决于导入时有没有元数据 | 检索侧透传 `doc_id` + `page`，低分不进 LLM |
| 数字 | Prompt「不要编」或 HTTP 调外部 | `lookup_metric` + 成稿后 `evidence.py` |
| 权限 | 工作空间 / 应用 Key | Java JWT + `X-Regops-Dept` + 检索裁剪 |
| 写操作 | 工作流 HTTP 节点可乱写 | 结论前 Checkpoint，只落 PENDING，双人复核 |
| 可测试 | 多为手工点画布 | 黄金集 + `--fail-on-regression`，主要评测不调 LLM |
| 延迟 | 平台检索 + 一次生成（起来后复跑填 P50） | 问数 0 token；RAG 含精排（现网精排 P50 约 +8.7s） |
| 成本 | 多一组容器（Postgres/Redis/Weaviate/api/worker）+ 同样的模型 Token | 已有 python-ai / Java / 一个 Postgres |
| 锁定 | 流程和知识库在平台里 | Prompt 钉扎 + 配置，可回滚 |

**何时用平台：** 标准问答、演示、运营自己改话术、不发版改流程。

**何时必须写代码：** 页级引用和拒答、财务数字零编造、部门 ACL、HITL 只写 PENDING、Java 双人复核、n=30 的 A/B 统计门禁。这些用 Prompt 或插件补不像，一补就锁进平台。

## 面试 q67（约 30 秒）

平台负责快，代码负责能测、能拦、能审计。我私有化起过 Dify，同一批公开年报进知识库，搭 RAG 和一个两步 Workflow，用 12 题同时打 Dify API 和自己的 `/chat`。比的是延迟、有没有页码、会不会拒答，不比「谁准确率更高」。主路径仍是自写：数字走事实库，引用走检索字段，工单走 Java。扣子 / HiAgent 是同类产品，没有再部署一套。

## 跑次数字

未起 Dify 时不要填假 P50。复跑后把 `eval/run_w8_dify_compare.py --write-example` 的摘要抄到这里，或看 `eval/dify/examples/last_compare.md`。

| 指标 | Dify | RegOps | 备注 |
|---|---|---|---|
| 延迟 P50 | （复跑后填） | （复跑后填） | 问数题本仓库应明显更快 |
| 要求带页码的题 | （复跑后填） | （复跑后填） | 本仓库 citations 带 page；Dify 看 retriever_resources |
| 应拒答的题 | （复跑后填） | （复跑后填） | 工行 / 招行不在本仓库 100 题语料主集 |

## 不做什么

- 不把 Dify 嵌进 `/chat` 或根 `compose.yaml`
- 不在 Dify 工作流里改工单状态
- 不把「Prompt 里写了不要编造」当成数字门禁
- 不把 Dify 官方示例准确率写进简历
- 不提交 `dify/upstream/`、知识库 blob、完整镜像
