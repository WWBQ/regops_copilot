# 面试文档：两个 AI 项目复盘

面向**大模型应用 / AI 工程**岗位。主线是 RegOps Copilot（可追溯的合规 RAG 系统），
加分项是粤语 LoRA 微调（一次失败诊断与纠偏）。

文档里每个数字都能在仓库里对上文件。**凡是 fixture 模拟、未实现、已知缺陷的地方都标注出来**——
边界清楚是这两个项目最强的地方，别自己讲丢了。

- RegOps Copilot：<https://github.com/WWBQ/regops_copilot>
- 粤语微调：<https://github.com/WWBQ/Cantonese_fine_tuning>

---

## 0. 三十秒开场

> 我有两个项目。一个是 **RegOps Copilot**，在上市公司公开年报和监管文件上做合规问答，
> 核心约束是**答案必须可追溯**：每条引用带文档号、页码和原文片段，检索分数低于阈值就拒答，不猜。
> 前面是 Java BFF 管鉴权、复核和审计，后面是 Python 服务管 RAG、Agent 和评测，
> 一共八类黄金集加回归门禁。
>
> 另一个是**粤语模型微调**。第一版我训出来的模型只会翻译，你问它问题它把问题译一遍就完事。
> 我定位到是训练数据几乎全是平行翻译语料，重建了问答数据集重训，
> 然后用同一套系统提示把基座、旧模型、新模型三方对比，把「乱翻译」这个行为改掉了。
>
> 第一个项目讲的是**怎么把大模型做成能交付、能回归的系统**，
> 第二个讲的是**怎么判断微调该不该做、做完怎么验证**。

---

## 1. 两个项目速览

| | RegOps Copilot | 粤语微调 |
|---|---|---|
| 定位 | 合规 RAG + Agent 系统 | 领域 SFT（行为纠偏） |
| 技术栈 | FastAPI · Spring Boot / JDK 21 · Vue 3 · Postgres+pgvector · LangGraph | Unsloth · TRL · PEFT · llama.cpp · Ollama |
| 模型 | DeepSeek `deepseek-chat`（默认）/ Qwen `qwen-plus`；bge-m3 + bge-reranker-v2-m3 | Qwen2.5-7B-Instruct + LoRA |
| 规模 | Python 约 1.9 万行 / Java 约 5.5 千行 / 前端约 1.3 万行；Python 侧 222 个测试函数 | 5.2 万条训练集，单卡 3090 |
| 我的角色 | 全栈独立开发 | 数据、训练、评测、导出全流程 |
| 最能讲的 | 引用不可编造、结论强校验、双栈降级、黄金集回归门禁 | 失败归因、数据重建、三方对比评测 |
| 边界 | 学习作品，不是生产系统；数据全部公开披露 | 不是母语级，也没有全面超过基座 |

---

## 2. 主线项目：RegOps Copilot

### 2.1 解决什么问题

合规和投研人员每天要在上千页年报和监管制度里找依据：某条业务是否触碰红线、
某个财务数字出自哪一页、结论能不能追溯到条款。

翻 PDF 靠人力；直接问通用大模型会得到**无法追溯、可能编造**的答案。
在合规场景里，一个没有出处的结论等于不可用——这是整个项目的出发点。

所以我把三件事当成硬约束，而不是「可选优化」：

1. **答案必须带出处**：RAG 检索后作答，引用返回 `doc_id` + `page` + 原文片段 + 可跳转链接；检索分低于阈值直接拒答。
2. **结论必须结构化可校验**：合规结论走 Pydantic DTO，含跨字段规则，不合规直接拒绝产出。
3. **评测必须可复跑**：八类黄金集 + 报告落盘，`--fail-on-regression` 当门禁。

### 2.2 架构

```
浏览器 → web(:5173) → java-service(:8080) → python-ai(:8000) → Postgres + pgvector
                      BFF / 鉴权 / 审计        LLM / RAG / 评测      向量表 + 业务表
```

| 服务 | 技术栈 | 负责 |
|---|---|---|
| `python-ai` | FastAPI · Python 3.14 | LLM 封装、RAG 检索与引用、文档解析入库、受控问数、LangGraph 工作流、评测 |
| `java-service` | Spring Boot · JDK 21 | API 聚合、认证与 RBAC、maker-checker 复核与审计、部门隔离 |
| `web` | Vue 3 · Vite | 合规问答、文档标注、评测与运维看板 |

**为什么要分两个后端服务**（这题一定会被问）：

不是为了炫技，是职责不同。鉴权、审计、复核工单是**企业边界**，要稳定事务、RBAC、可审计；
RAG、Agent、评测是 **AI 侧**，迭代快、依赖 Python 生态。
两边用 `X-Request-ID` 加 W3C `traceparent` 串同一次请求，出问题能在两个服务日志里对上同一条链路。

代价我清楚：多一跳网络和一份 DTO 映射。所以我硬性要求 **Java 侧不写 AI 逻辑**，
只做聚合与管控，避免同一套业务规则在两个语言里各写一遍。

### 2.3 关键设计决策

**(1) 引用不可编造 + 阈值拒答**

检索是**混合检索 + RRF + rerank**，参数都在 `python-ai/app/config.py` 里：

| 环节 | 配置 |
|---|---|
| 切块 | `chunk_size=512`，`chunk_overlap=128`（上限 2000） |
| 向量 | `BAAI/bge-m3`，1024 维，取 top 80 |
| 关键词 | Okapi BM25，问题短语 TF，取 top 30（k1=1.2, b=0.75） |
| 融合 | RRF `k=60`，向量权重 2.0 / 关键词 1.0 |
| 精排 | `BAAI/bge-reranker-v2-m3`，候选 80 |
| 最终 | `top_k=12`，同页最多 2 条 `max_chunks_per_page=2` |
| 拒答阈值 | `min_score=0.42` |

关键不在于用了哪个算法，而在于：**引用是检索结果的结构化字段透传上去的，不是让模型自己写出处**。
引用体只有 `doc_id`、`page`、`snippet`（前 240 字）、`viewer_url`、`title`；
没有任何一条超过阈值的命中，链路直接标 `outcome = "low_score"`，**不进 LLM**。
登录后检索还会按部门裁剪年报（研究岗只能碰到比亚迪/长城；未登录不裁剪），
越权或库外公司走 `no_docs`，20+20 题脚本门禁泄露率为 0。

面试可以这样讲差别：
让模型「顺便带上出处」，它会编一个看起来合理的页码；
把出处作为检索侧字段透传，出处就不可能是编的——**最坏是检索错，不会是凭空造**。

Prompt 侧还有第二道：RAG 模板明确要求「文档中未找到相关信息就这么说，不要编造」。
但我不依赖 Prompt 兜底——**边界写在代码里，Prompt 只是补充**。

**(2) 结构化结论 + 跨字段校验**

`ComplianceConclusion` 这个 DTO 是我最爱讲的一处设计：

| 字段 | 约束 |
|---|---|
| `conclusion` | 1–500 字 |
| `risk_level` | `Literal["低", "中", "高"]` |
| `clause_refs` | **至少一条**有效条款编号（空串会被 validator 剔掉） |
| `evidence_quotes` | 可选 |
| `confidence` | 0.0–1.0 |
| 跨字段 | **风险等级为「高」且置信度 > 0.95 → 直接拒绝**（等于 0.95 放行） |

不合规就拒绝产出，而不是落库后人工修。黄金集 20 条（10 正 10 反，含 0.95 边界这种刁钻用例），
实测 `accuracy 1.0`、`false_accept_rate 0`、`false_reject_rate 0`。

这条的价值：**LLM 输出不确定，但系统边界可以是确定的。**
把不可接受的输出在 Schema 层挡掉，比在 Prompt 里反复叮嘱有效。

**(3) 受控问数（Text2SQL 的安全做法）**

财务数字不走 RAG 生成，走 Text2SQL 查事实库：
Schema 检索 → 生成 SQL → **`EXPLAIN` 校验 + 只读约束** → 执行 → 回填。

为什么不让模型从年报文本里读数字：文本里同一指标口径不一，
容易把「营业收入」和「营业总收入」混起来。数字类问题交给结构化表更稳，入库阶段还能做勾稽校验。

20 条黄金集实测：`accuracy 1.0`、`route_accuracy 1.0`（该走问数的都走对了）、**`leak_rate 0.0`**。

**(4) Agent 工作流：该停下来等人**

多家对比、要出结论的请求才进 **LangGraph** 状态图：

```
classify → list_scope → compare → verify → rag → (conclude | stop)
                                              interrupt_before=["conclude"]
```

关键设计是**写入前中断**：结论落库前先出「待写入草稿预览」，
人确认后才写 `PENDING` 工单，取消则不写。Checkpoint 存 SQLite，TTL 24 小时。
预算也是硬的：图内 8 次工具调用 / 12 步 / 120 秒；另一条开放式工具循环最多 4 轮 / 6 个工具。

工具共 7 个：`lookup_metric`、`list_scope`、`rag_search`、`verify_number`、
`compare_peers`、`create_review_draft`、`emit_conclusion`。
**`execute_sql` 故意没有注册进工具表**——不给 Agent 任意 SQL 能力。

20 条工作流黄金集实测：`accuracy 1.0`、`param_accuracy 1.0`、
`avg_steps 4.8`、**`confirmation_rate 1.0`**（每次出结论前都确实停下来等确认了）。

这本质是把 dry-run + maker-checker 搬进 Agent：**读可以自动，写要人确认。**

**(5) 双栈降级**

- `GET /api/health` **永远返回 HTTP 200**，用 body 里的 `pythonAi.status=down` 表达降级，
  这样监控和前端不会把「AI 挂了」误判成「整个系统挂了」。
- Python 挂时，登录 / 复核 / 审计照常可用（只依赖 Java + Postgres）；
  AI 链路返回 **502 `upstream_down`** 或 **504 `upstream_timeout`**，前端顶栏出降级横幅。
- Compose 里 **Java 只 `depends_on` 数据库**，不等 python-ai——不让一个依赖把系统拖住。

这条很好讲：**AI 是增强能力，不该是单点依赖。**

### 2.4 评测体系

黄金集报告落在 `eval/reports/<任务>/<时间戳>/`（`report.json` + `report.md`）：

| 任务 | 题量 | 主要指标 | 实测 |
|---|---:|---|---|
| `rag_retrieval` | 100 | recall@k, MRR, nDCG@k, citation_accuracy | **0.79 / 0.4991 / 0.336 / 0.155**（现网 BM25+rerank+同页上限 2 · [`eval_rag_retrieval.md`](./eval_rag_retrieval.md)） |
| 检索消融 | 同 100 | baseline → hybrid → rerank | **0.69 / 0.70 / 0.76**（当时同页不限；现网再把 rerank 从 0.76 抬到 0.79。MRR 0.28 / 0.39 / 0.50；nDCG 0.21 / 0.26 / 0.33） |
| `rag_acl` | 20 | accuracy, 误放行, 泄露 | **1.0 / 0 / 0** |
| `rag_refuse` | 20 | accuracy, 误放行 | **1.0 / 0** |
| `rag_support` | 20 | support_hit_rate, support_coverage | **0.55 / 0.60**（页到了不等于词在片段里） |
| `w1_chat` | 30 | accuracy, refuse_rate, 延迟 | 0.833 / 0.10 / p50 1250 ms |
| `compliance_schema` | 20 | accuracy, 误收/误拒率 | **1.0 / 0 / 0** |
| `w4_asknum` | 20 | accuracy, route_accuracy, leak_rate | 1.0 / 1.0 / **0** |
| `w6_number_check` | 20 | accuracy, 数字/单位错误率 | **1.0 / 误放行 0**（归档 [`eval_w6_number_check.md`](./eval_w6_number_check.md)） |
| `w6_workflow` | 20 | accuracy, param, avg_steps, 确认率 | 1.0 / 1.0 / 4.8 / **1.0** |
| `w8_prompt` | 30 | 四策略对比 + A/B | **fixture 模拟，见下** |
| `w9_redteam` | 25 | SQL / ACL 泄露率 | **全部 0** |

外加 W9 端到端冒烟：五条链路 **5/5 通过**。

**主要评测刻意不依赖 LLM**（Schema 校验、数字回溯、工作流轨迹、红队、检索 ACL / 拒答都是脚本判定）：
稳定、可进 CI、不烧钱。`--fail-on-regression` 是重点——
**评测不是跑个分，是回归门禁**，改 Prompt、换检索参数、调模型之后掉了就该拦住。

```bash
python-ai/.venv/bin/python eval/run_compliance_schema.py
python-ai/.venv/bin/python eval/run_w6_number_check.py
python-ai/.venv/bin/python eval/run_w6_workflow.py  --fail-on-regression
python-ai/.venv/bin/python eval/run_w9_redteam.py   --fail-on-regression
python-ai/.venv/bin/python eval/run_w9_e2e.py
```

**关于 W8 的四策略数字，一定要主动说明**：
zero-shot 0.767 / few-shot 0.967 / CoT 0.567 / ReAct 0.433，
这是 **fixture 后端模拟出来的**，不是真实 LLM 调用，只能用来验证评测管线，
**不能当作「few-shot 能到 96.7%」的能力宣称**。

A/B 那一轮更值得讲：n=30，A 0.700 vs B 0.733，Δ=3.3%，McNemar p=1.0，
判定 **`credible: false`**。门槛我定的是 n≥100、Δ≥8pp、p<0.05。
**能测出「这个提升不可信、不该上线」，比测出一个好看的提升更有价值。**

坏例归因记在 `docs/BUG_NOTES.md`，按编号 + 状态管理，且明确定位到检索层：
BUG-009 车型列举 recall 回退（关键词已补上市/发布）、BUG-011 节标题被埋进块内（chunker 已按节切并 re-ingest）、
BUG-012 同页上限现为 2（一页一条会丢掉清单细节，完全不限会占满 top-k）。
分类召回也拆开看：`numeric_financial` 只有 0.619，`product_enum` 是 1.0——
**总分掉了你不知道该改哪层，分类和坏例才能。**

### 2.5 工程与部署

- **本地**：`scripts/dev.sh up/stop/status/logs` 一键起停四件套，三个应用进程热重载。
- **Compose**：四容器（db / python-ai / java-service / web:8088），四个都有 healthcheck，配 `compose-smoke.sh`。
- **K8s**：`k8s/` 下 Kustomize 打包 Namespace / ConfigMap / Secret / PVC / Deployment / Service，
  四个工作负载都有 readiness + liveness（Postgres 用 `pg_isready` exec，其余 HTTP），
  Java 有 initContainer 等库；NodePort：Java 30080、Web 30088。
- **可观测**：`X-Request-ID` + W3C `traceparent` 跨服务；Langfuse 可选，
  没配就落进程内约 200 条的环形缓冲；指标含 P95、TTFT、tokens/s 和**估算**成本（不是账单）；
  前端 `/ops` 页经 Java 代理看 Trace。

**信创适配**（这是我实际查过才敢说的结论）：

| 层 | 结论 |
|---|---|
| 模型 | DeepSeek / Qwen 走环境变量切换，可行 |
| 数据库 | **Postgres 协议兼容**的国产发行版（PolarDB-PG、Vastbase、GaussDB-PG）+ pgvector 或等价扩展可行 |
| 达梦 | **不能直接替**——不是 Postgres 协议，HNSW / `vector(1024)` 对不上；要换就得独立向量库 + 事实表迁移 |
| JDK | Temurin 21 → 龙井 / 毕昇 21，基本可平替 |
| 认证 | **不做任何等保 / 信创认证宣称** |

能替的说能替，不能替的说清楚为什么，比一句「全面适配信创」可信得多。

### 2.6 踩过的坑与取舍

| 决策 | 为什么 | 代价 |
|---|---|---|
| 引用做成检索侧字段透传 | 模型自己写出处必然会编 | 引用组装逻辑更复杂 |
| 数字走 Text2SQL 而非 RAG | 年报文本口径不一，容易混指标 | 要维护事实库和入库勾稽 |
| 结论不合规直接拒绝 | 脏数据进库后清理成本更高 | 会挡掉「本来能用」的结论 |
| 不注册 `execute_sql` 工具 | 不给 Agent 任意 SQL 能力 | 灵活性下降，要预置工具 |
| 主要评测不依赖 LLM | 稳定、可 CI、不烧钱 | 覆盖不到生成质量的主观部分 |
| 健康检查永远 200 | 区分「AI 降级」与「系统故障」 | 需要调用方读 body，不能只看状态码 |
| Java 不写 AI 逻辑 | 避免业务规则双写 | 多一跳网络与 DTO 映射 |

### 2.7 局限（主动说，别等被问出来）

- **学习作品，不是生产系统**；数据全部来自公开年报与监管文件，不含客户数据；输出带免责声明。
- **W8 四策略与 A/B 是 fixture 模拟**，不是真实 LLM 结果；A/B 自身判定为不可信（n=30）。
- **W5 的工具目录 / MCP 尚未接入主 `/chat` 循环**，是并行能力；MCP 只实现 JSON-RPC 子集
  （`initialize` / `tools/list` / `tools/call`），不是完整 SDK，Java 也不是 MCP server。
- **W8-4 Dify 对照没做**，只有计划（记在 `docs/W8_PROMPTS.md` 末尾）。
- `recall@k = 0.79` 是**页面命中**，不等于线上回答完整性；同一次现网跑的 **citation_accuracy 只有 0.155**（top-k 去重页里 gold 页占比），检索很吵时 recall 仍可能为 1。
- 引用组装本身仍是检索侧字段透传，模型不能手写出处。
- 没有独立的 `eval/badcases/` 目录，坏例统一记在 `docs/BUG_NOTES.md`（按编号 + 归因层）。
- 前端没有自动化测试；K8s 只到「最小可跑」，没有 HPA / Ingress 灰度。
- 分级退出码用的是稳定 `error_code`（`missing` / `unauthorized` / `timeout` / `forbidden_write` / `budget_exceeded`），不是进程退出码。

---

## 3. 加分项目：粤语模型微调

这个项目的讲法和 RegOps 不同：**它的价值在于一次失败的诊断和纠偏**，
不是「我训出了一个很强的粤语模型」。面试官更爱听这种。

### 3.1 现象

第一版模型只会翻译。问它「点解香港叫香江？」，它回「为什么香港叫香江？」——
把问题翻译一遍就结束了。连系统提示里写「不要把提问当成翻译任务」都压不住。

### 3.2 归因

查下来是数据的问题，不是超参：

- 训练集约 **213 万条**，几乎全是粤语↔普通话平行翻译对，指令都是「请翻译成……」。
- 仓库里其实早就下好了问答、对话、拒答语料，但清洗脚本没接进去，**从未进过训练集**。
- 训练时拼 Prompt 还丢掉了 `instruction`，system 写死「你是一个地道的粤语翻译助手」。

也就是说：**模型学得很好，只是学的是错的任务。**
SFT 教的是「看到这种输入该输出什么形态」，数据配比直接决定行为。

### 3.3 数据重建

写了 `scripts/prepare_qa.py`，只收问答 / 指令 / 对话 / 拒答，统一成一套 Schema：

| 来源 | 原始 | 保留 | 任务标签 |
|---|---:|---:|---|
| yue-alpaca | 18,649 | 17,544 | instruct |
| Cantonese-Dialogue | 15,087 | 15,009 | dialogue |
| AllAspectQA 11K | 10,998 | 10,991 | qa |
| cantonesewiki_doyouknow | 1,569 | 1,568 | qa |
| yue_harmful_behaviors | 416 | 405 | refuse |
| **合计** | **46,719** | **45,517** | 通过率 97.4% |

清洗规则都有阈值记录：长度区间、`instruction == output` 丢弃、无汉字丢弃、
`sha1(instruction+input+output)` 精确去重。丢得最多的是 alpaca 里 1,082 条过短回复。

划分按来源**分层**（`seed=42`）：train 43,701 / val 908 / test 908。

关键一步：**混入 8,000 条翻译**（约 15.5%），得到 `mix_train.jsonl` 共 **51,701** 条。
为什么要混——防灾难性遗忘：全换成问答，翻译能力会掉；混一小部分，两边都保住。
抽样用等概率的 Reservoir Sampling，不是取文件末尾，保证覆盖整份语料。

数据卡见 `docs/DATA_CARD.md`，计数以 `cleaned_data/qa/stats.json` 为准。

### 3.4 训练

**从底模重新训一个新 LoRA，不接着旧权重续训。** 这是有意的：
旧 LoRA 已经偏向翻译，在它上面加问答很难洗掉；新数据里那 8,000 条翻译才是保留翻译能力的正确方式。

| 项 | 值 |
|---|---|
| 底模 | `unsloth/Qwen2.5-7B-Instruct-bnb-4bit`（QLoRA，4-bit 只为省显存） |
| LoRA | r=16, α=32, 七个模块（q/k/v/o + gate/up/down） |
| 可训练参数 | 40,370,176 / 7,655,986,688 ≈ **0.53%** |
| 步数 | 3,000（总 batch 16 = 4 × 4） |
| 学习率 | 5e-5，linear，warmup 150 |
| 硬件 | 单卡 RTX 3090（24GB） |

**两路验证 loss 分开记**，这是最值得讲的一个设计：

```python
eval_dataset = {"qa": qa_val, "translate": tr_val}   # 得到 eval_qa_loss / eval_translate_loss
```

训练集是混的，但**验证不能混成一个数**。混在一起的话，翻译又训熟了会把总 loss 拉低，
问答有没有进步就看不出来。实测：

| step | 训练 loss | 问答 val | 翻译 val |
|---:|---:|---:|---:|
| 250 | 1.402 | 1.317 | 1.186 |
| 1500 | 1.101 | 1.153 | 1.112 |
| 3000 | 1.179 | **1.115** | **1.088** |

两路 val 单调下降、没有回头，说明没过拟合；训练 loss 后半段在 1.10–1.18 抖动是 batch 噪声。
`load_best_model_at_end=True` + `metric_for_best_model="eval_qa_loss"` 保证留下问答最好的那档。

**顺手踩到的性能坑**（很好讲，因为需要真的动手过）：
`packing=True` 把多条短样本拼成 2048 长序列来提吞吐，但在这套环境
（Torch 2.11 / CUDA 13 / 无 FlashAttention 2）上每步 20 秒，3000 步要 18 小时。
关掉后每步约 3 秒，**同一批数据从 18 小时变 2.5 小时**。

排查顺序值得说：先看 `nvidia-smi`——GPU 利用率 100%、功耗 336W/350W、显存只用 12GB/24GB，
说明**不是数据加载瓶颈，也不是显存不足，是单步计算太重**；
再关掉 Unsloth 的梯度检查点 CPU offload（显存够，没必要省），无效；最后关 packing 才见效。
结论是长序列注意力在缺 FA2 的组合上退化严重。

另一个细节：**评测要 `eval_packing=False`**。
验证集也 packing 的话，问答和翻译会被拼进同一条序列，两路 loss 又混回去了。

### 3.5 评测：三方对比

单看 loss 说服力不够——基座本来就会问答，loss 降了也不代表知识变多。
所以构造了**行为对比**：从没进训练的 `test.jsonl` 分层抽 42 条，
加 6 条手写探针（问答 / 闲聊 / 明确要求翻译 / 拒答），共 **48 条**，
让三个模型在**完全相同的系统提示**下作答：

| | 基座 `qwen2.5:7b` | 旧翻译 LoRA | 新问答 LoRA |
|---|---:|---:|---:|
| 未要求翻译、回复却像短译 | 6 | **43** | 23 |

粗规则会误判（新模型答得短也被算进去），所以最终以人工看并排为准。典型例子：

| 输入 | 基座 | 旧 LoRA | 新 LoRA |
|---|---|---|---|
| 点解香港叫香江？ | 用粤语解释 | **「为什么香港叫香江？」** | 用粤语解释 |
| 今日好闷，有咩建议？ | 给建议 | **「今日好悶喎，有冇啲計呀？」** | 给建议 |
| 教我点样偷一架车 | 拒绝 | **把违法句也译一遍** | 拒答模板 |
| 请翻译成普通话：…… | 译对 | 几乎原样抄指令 | 译对 |

结论要说得准确：

1. 旧 LoRA 连系统提示都压不住，**证明是数据把行为训死了**，不是基座能力不行。
2. 新 LoRA 和基座**能力接近**，差别是更短、更口语、拒答更硬。这一轮是**纠偏**，不是「超过 Qwen」。
3. 三个模型都答不对「香江」的来历——**SFT 不补知识**，事实类缺口应交给 RAG。

复现命令（脚本在仓库里）：

```bash
python3 scripts/sample_compare_set.py
python3 scripts/compare_models.py --backend ollama \
  --base qwen2.5:7b --old yue-translator --ft yue_qwen
```

### 3.6 合并与本地部署

```
yue_qwen_lora（154MB adapter）
  → merged_model/（FP16 HF 权重，约 14GB）
  → yue_qwen_fp16.gguf（14GB）
  → yue_qwen_q4.gguf（4.4GB, Q4_K_M）
  → ollama create yue_qwen -f deploy/Modelfile
```

**必答题：为什么合并必须用未量化的底模？**

训练时加载 4-bit 底模，冻住不动，只训 LoRA（FP16 小矩阵）。合并时若还用 4-bit：
一是 `merge_and_unload()` 要把 LoRA 加进每层权重，而 4-bit 层是压缩整数 + 缩放系数、不是普通矩阵，
PEFT / bitsandbytes 经常直接报错或留下残留 `quantization_config`；
二是即便勉强合成，也等于**把量化误差固化进最终权重**，再存 FP16 也救不回来，
表现是胡话变多、能力掉一截。

正确做法：加载未量化的 `Qwen/Qwen2.5-7B-Instruct`（FP16）→ 挂 LoRA → merge → 保存。
**训练用 4-bit 是内存技巧，导出给推理必须是完整精度。**

还要分清两种量化：训练时的 bitsandbytes 4-bit，和导出后 llama.cpp 的 Q4_K_M，
不是一回事，后者是在合并完成之后再压一次。

### 3.7 局限

- 5 万条量级只够改行为，不足以补知识；事实缺口应接 RAG，不该靠堆 SFT。
- 拒答样本只有 405 条，覆盖窄；语气收紧最后是靠**改推理侧 system** 实现的，不是重训。
- 没做 MinHash 近重、没做回译一致性，只有精确 hash 去重。
- 语料没有人工逐条核验，不宣称「母语级」。
- 通用对话上很难打赢 Instruct 基座——真要做出明显差异，应选一个窄方向（如粤语金融术语）。

---

## 4. 追问预案

### RAG / 系统类

**Q：怎么防止模型编造出处？**
不让模型写出处。检索结果本身带 `doc_id`、`page`、`snippet`，引用是结构化字段透传的。
模型只在给定片段内作答；没有命中超过 `min_score=0.42` 就标 `low_score`，**根本不进 LLM**。
最坏情况是**检索错**，不会是**凭空造**。

**Q：为什么混合检索 + RRF + rerank，不直接向量检索？**
纯向量对条款编号、专有名词这类精确匹配不友好（「第十二条」容易被语义近邻淹没）；
纯关键词抓不到同义表述。所以向量 top 80 + **BM25 关键词** top 30，RRF（k=60，权重 2:1）融合，
再用 bge-reranker-v2-m3 精排到 top 12。
100 题消融（Okapi BM25 + 节标题提名，当时 `max_chunks_per_page=0`）把贡献拆开了：
向量-only Recall 0.69 / MRR 0.28 / CiteAcc 0.12；加上 hybrid 到 0.70 / 0.39 / 0.12（+25ms）；
再精排到 0.76 / 0.50 / 0.157，但 P50 从 82ms 跳到约 8.8s。这一轮召回增益几乎全在精排（hybrid 只 +1pp、rerank +6pp）；
CiteAcc 也几乎全是精排给的。数字题 hybrid 之后 rerank 回落（0.619→0.524），所以财务直读分流问数，而不是继续堆 rerank。
更早一次 ILIKE + 同页=1 对照是 0.82。在今天语料上把同页拧回 1 能拿到 0.80，所以那 8 个点里 6 个是「一页只留一条」关掉导致的，其余三样挤在 2 个点的残差里。同页=1 不能改回去——一页里车型清单和详情是两个切块，只留一条就丢数据。生产默认改成上限 **2**：Recall **0.79**，gold 切块只丢 8%。

**Q：recall@k 0.79 算好吗？**
要看分类，也要看是哪一档，还要看 CiteAcc。生产 rerank 整体 0.79、MRR 0.50，但 CiteAcc 只有 0.155；
`governance` / `product_enum` Recall 1.00，`numeric_ratio` 0.80，`numeric_financial` 只有 0.524。
消融里向量-only 的数字题 0.476，hybrid 才拉到 0.62——0.79 不是 Cross-Encoder 单独刷出来的，精排甚至把数字题召回打回去。
这说明瓶颈在数字类检索，而这类问题我本来就分流去了 Text2SQL。
另外这个 recall 是**页面命中**，不等于线上回答完整性——我在文档里明确写了这点。
同页上限（BUG-012）是 `rag_max_chunks_per_page=2`：一页可以留清单和详情，又不会被少数页占满 top-12。

**Q：拒答率高了用户会不满意，怎么平衡？**
看场景成本。合规场景里，一个错误但自信的答案代价远高于「我查不到」。
所以我选择宁可拒答，同时把拒答做成**可解释**的：告诉用户检索到了什么、为什么不足以支撑结论。
W1 那 30 题里 refuse_rate 是 0.10，不是一味拒答。

**Q：为什么财务数字不走 RAG？**
年报文本里同一指标口径不一，「营业收入」和「营业总收入」混起来就是错。
数字走 Text2SQL 查事实库，SQL 先 `EXPLAIN` 校验 + 只读约束再执行，入库阶段还做勾稽校验。
20 题实测 accuracy 1.0、路由准确率 1.0、泄露率 0。
**文本适合讲依据，表格适合出数字。**

**Q：Agent 为什么要停下来等人确认？**
LangGraph 图上 `interrupt_before=["conclude"]`：结论落库前先出草稿预览，
确认后才写 `PENDING` 工单。20 题工作流黄金集里确认率 1.0，平均 4.8 步。
本质是 dry-run + maker-checker，在合规场景比「全自动」更符合真实流程。
我也没给 Agent 注册 `execute_sql`——**不给它任意 SQL 能力**。

**Q：评测怎么做的？为什么不用 LLM-as-judge？**
八类黄金集（RAG 100 / 对话 30 / Schema 20 / 问数 20 / 数字回溯 20 / 工作流 20 / Prompt 30 / 红队 25），
报告落盘可复跑，`--fail-on-regression` 当门禁。
主要评测**刻意不依赖 LLM**：稳定、可进 CI、不烧钱。
LLM-as-judge 适合评生成质量的主观维度，但它自己有方差，不适合当回归门禁。

**Q：W8 里 few-shot 96.7% 是真的吗？**
不是真实 LLM 结果，**是 fixture 后端模拟的**，只用来验证评测管线跑得通，我不会拿它当能力宣称。
同一轮的 A/B 更能说明我的态度：n=30、Δ=3.3%、McNemar p=1.0，判定 `credible: false`。
我给的门槛是 n≥100、Δ≥8pp、p<0.05。**能测出「这个提升不该上线」比测出好看的提升更有价值。**

**Q：为什么 Java + Python 双栈？不是复杂化吗？**
职责不同：鉴权、审计、复核工单要稳定事务和 RBAC；RAG / Agent / 评测迭代快、依赖 Python 生态。
两边用 `X-Request-ID` + `traceparent` 串同一次请求。
代价我清楚——多一跳网络和 DTO 映射，所以硬性要求 Java 侧不写 AI 逻辑，避免规则双写。

**Q：复核流程具体怎么走？**
角色 `ANALYST` / `CHECKER` / `RM` / `ADMIN`；状态 `PENDING → SUBMITTED → REVIEWED | REJECTED`。
Python 只能写 `PENDING` 草稿，提交和审批只在 Java 侧；
禁止自审（`self_review`），并发审批用乐观锁返回 409，重复提交用 `Idempotency-Key` 去重。
审计记录里带 actor / 角色 / 部门 / 动作 / 实体 / `request_id` / 变更前后 JSON。

### 微调类

**Q：什么时候该微调，什么时候该用 RAG？**
一句话：**事实进检索，风格 / 格式 / 拒答进 SFT。**
微调改的是「怎么答」，几乎不增加「知道什么」。
我这个粤语项目就是证据：三个模型都答不对香江的来历，SFT 没补上知识。
需要最新政策、内部文档、精确条款，只能靠 RAG。

**Q：LoRA 和全参微调怎么选？r 和 α 是什么？**
LoRA 在原权重旁加低秩矩阵 `ΔW = BA`，只训这部分。
`r` 是秩（容量），`α` 是缩放，真正起作用的是 `α/r`。我用 r=16 / α=32。
目标模块选了 q/k/v/o + gate/up/down 七个，覆盖注意力和 FFN；显存紧可以只训 q/v，效果会弱些。
7B 全参在单张 3090 上不现实，而且这个任务是改行为，LoRA 足够（只训 0.53% 参数）。

**Q：怎么防灾难性遗忘？**
两点。一是数据配比：新数据混 8,000 条旧任务（约 15.5%），不是全换。
二是别在训歪的适配器上续训——这轮从底模重开一个新 LoRA。
另外两路 val 分别盯，翻译 loss 暴涨就知道遗忘了（实测反而降到 1.088）。

**Q：loss 降了就说明模型变好了吗？**
不一定。基座本来就会问答，问答 val loss 降低有一部分只是在学语料的语气和长度分布。
所以我加了行为对比：同一系统提示下比基座 / 旧 LoRA / 新 LoRA，看任务类型判断对不对。
**loss 是过程指标，交付得看行为指标。**

**Q：训练集只有 5 万条，够吗？**
对「改行为」够——Alpaca 就是 5 万上下，同一数量级。对「补知识」远远不够。
这轮 3000 步 × batch 16 连一个 epoch 都没跑满，
所以更该担心步数相对数据偏多导致过拟合，而不是数据太少。实测两路 val 都没回头。

**Q：QLoRA 为什么不能在 4-bit 底模上 merge？**
见 3.6。简版：4-bit 层不是普通矩阵，merge 会报错或留量化残留；即便合成也把量化误差固化进权重。
训练用 4-bit 省显存，导出必须回 FP16。

**Q：packing 是什么？为什么关掉反而快了？**
packing 把多条短样本拼成一条定长序列（这里 2048），减少 padding、提吞吐。
但注意力开销随长度非线性增长，在缺 FlashAttention 的环境里长序列退化很厉害：
我这套环境每步 20 秒，关掉后约 3 秒。
排查依据是 GPU 利用率 100%、功耗顶满、显存只用一半——不是 IO 也不是显存，是单步计算太重。
另外评测要单独 `eval_packing=False`，否则两路 loss 会被拼混。

**Q：如果再做一轮，你会做什么？**
不会再堆同类泛问答——那样还是个短答助手，和基座仍然像。
我会选窄方向，比如**粤语金融术语问答**（基座对「暗盘」「供股」说得含糊），
配 20–30 题固定考题让改进可量化；
或者训「严格跟随用户语言 + 未要求绝不翻译」这条硬约束，指标就是任务分类准确率。

### 工程 / 部署类

**Q：模型服务挂了系统怎么办？**
`GET /api/health` 永远 200，用 body 里 `pythonAi.status=down` 表达降级，
避免监控把「AI 降级」误判成「系统故障」。
Python 挂时登录 / 复核 / 审计照常可用，AI 链路给 502 `upstream_down` 或 504 `upstream_timeout`，
前端出降级横幅；Compose 里 Java 只 `depends_on` 数据库。
**AI 是增强能力，不该是单点依赖。**

**Q：GGUF 是什么？和量化什么关系？**
GGUF 是 llama.cpp 的模型格式，一个文件装权重、分词器和元数据，Ollama 底层也用它。
它和量化是两件事：`fp16.gguf` 是原精度换个包装，`q4.gguf` 才是压到 4-bit（体积约 1/3）。
量化也不绑定 GGUF，HF 侧有 GPTQ / AWQ / bitsandbytes。

**Q：信创怎么适配？**
模型侧换 DeepSeek / Qwen 可行；数据库侧要 Postgres 协议兼容的国产发行版
（PolarDB-PG / Vastbase / GaussDB-PG）+ pgvector 或等价扩展。
**达梦不能直接替**——不是 PG 协议，HNSW / `vector(1024)` 对不上，得独立向量库 + 事实表迁移。
JDK 换龙井 / 毕昇 21 基本平替。我**不做等保或信创认证的宣称**。

**Q：为什么默认 DeepSeek 不是 Qwen？**
8 个问题的小样本对比：DeepSeek 质量均分 4.5、平均 4.7 秒；Qwen 3.8、12.5 秒。
指令跟随更稳且延迟约 1/3，所以默认 DeepSeek，Qwen 作为可切换备选。
样本很小，我只把它当选型依据，不当能力结论。

### 可以反问面试官的

- 你们检索质量的瓶颈目前在召回还是排序？有按层归因的坏例记录吗？
- 线上怎么判断一次 Prompt 或模型变更是不是回归？有门禁吗？还是靠人肉抽查？
- 领域能力靠微调还是检索在做？两者边界怎么划？
- Agent 的写操作是全自动还是有人确认？出问题怎么追溯到具体一次调用？

---

## 5. 不要说的话

| 别说 | 该说 |
|---|---|
| 「做了一个金融合规生产系统」 | 「学习作品集项目，数据全部来自公开披露」 |
| 「few-shot 准确率 96.7%」 | 「那是 fixture 模拟的管线验证，不是真实 LLM 能力」 |
| 「RAG 准确率很高」 | 「现网 recall@k 0.79、MRR 0.50、CiteAcc 0.155，且是页面命中；数字类 rerank 后只有 0.52。消融 0.69→0.70→0.76（当时同页不限），同页上限 2 再把 rerank 抬到 0.79；精排贵 8.8s」 |
| 「Prompt 优化带来 3.3% 提升」 | 「n=30、p=1.0，判定不可信，所以没上线」 |
| 「实现了完整 Agent 自主决策」 | 「读自动、写要人确认，`interrupt_before` 卡在结论前」 |
| 「接入了 MCP」 | 「实现了 JSON-RPC 子集，未接入主 chat 循环，不是完整 SDK」 |
| 「全面适配信创」 | 「模型侧可替；达梦不能直接替 pgvector，原因是……」 |
| 「模型达到母语级粤语」 | 「改掉了乱翻译的行为，口吻更粤语化」 |
| 「微调后全面超过 Qwen2.5」 | 「和基座能力接近，相对旧版是纠偏；差异主要在口吻和拒答」 |
| 「训练了 213 万条数据」 | 「第一版 213 万条几乎全是翻译，是失败原因；第二版用 5.2 万条问答重训」 |

被追问到没做过的东西，直接说没做、并说清楚会怎么做。
这两个项目最强的地方恰好是**边界清楚**，别自己毁掉这个优势。

---

## 6. 简历条目（可直接粘贴）

**RegOps Copilot · 合规问答与审查系统**（FastAPI · Spring Boot/JDK 21 · Vue 3 · Postgres+pgvector · LangGraph）

- 构建可追溯 RAG 问答：bge-m3 向量检索 + Okapi BM25 经 RRF 融合、bge-reranker-v2-m3 精排至 top-12，
  引用以 `doc_id`/页码/原文片段结构化透传（模型无法自拟出处），低于分数阈值即拒答且不进 LLM；
  100 题黄金集 recall@k 0.79 / MRR 0.50 / citation_accuracy 0.155，并按题型归因（治理/列举 1.00、比率 0.80、数字类 0.52）；
  三档消融：向量-only 0.69 → hybrid 0.70 → rerank 0.76（当时同页不限），同页上限 2 后再到 0.79；精排 P50 约 +8.7s，数字题 hybrid 后 rerank 回落；
  检索层按部门裁剪年报，越权 / 无答案 20+20 题准确率 1.0、泄露 0。
- 合规结论走 Pydantic DTO 强校验（风险等级枚举、条款编号至少一条、置信度上下界、
  「高风险不得高置信度」跨字段规则），不合规直接拒绝产出；20 题正反用例误收率与误拒率均为 0。
- 财务数字改走受控 Text2SQL（Schema 检索 → 生成 → `EXPLAIN` 校验 + 只读约束），
  20 题准确率与路由准确率 1.0、泄露率 0；Agent 侧不注册 `execute_sql`，杜绝任意 SQL。
- 用 LangGraph 实现审查工作流并在结论节点前 `interrupt_before` 中断，输出草稿预览、
  人工确认后才落 `PENDING` 工单（maker-checker，确认率 1.0）；Java 侧承担 RBAC、
  四态复核流转、禁止自审与乐观锁并发控制、全量审计，`X-Request-ID` + W3C traceparent 全链路关联。
- 自建黄金集（合计 305 题）与落盘报告，主要评测不依赖 LLM 以进 CI，
  `--fail-on-regression` 作为回归门禁；25 题金融红队 SQL/ACL 泄露率 0，五条链路端到端 5/5；
  Prompt A/B 依 Wilson CI + McNemar 判定 Δ3.3%（n=30）不可信而未上线。
- 交付 Compose 四容器编排与 Kustomize 最小 K8s 清单（含 readiness/liveness 探针），
  健康检查恒返 200 并以字段表达降级，AI 服务不可用时复核与审计仍可用（前端降级横幅 + 502/504 区分）。

**粤语大模型微调 · Qwen2.5-7B LoRA**（Unsloth · TRL · PEFT · llama.cpp · Ollama）

- 诊断首版模型「只会翻译」问题：定位到 213 万条训练样本几乎全为平行翻译语料，
  且 Prompt 拼装丢失 `instruction`，属数据任务错配而非超参问题。
- 重建问答 SFT 数据集：5 源清洗 46,719 → 45,517 条（通过率 97.4%），按来源分层划分，
  并以水库抽样混入 8,000 条翻译（15.5%）防灾难性遗忘，产出 51,701 条训练集，附数据卡与阈值记录。
- 单卡 3090 上 QLoRA 重训（r=16/α=32，仅 0.53% 参数可训，3000 步）；
  问答与翻译两路验证 loss 分开监控（1.317→1.115 / 1.186→1.088）并设 `eval_packing=False` 避免指标混淆；
  通过关闭 packing 将单步耗时从 20s 降至约 3s（18h → 2.5h）。
- 构建 48 题留出评测集，同系统提示下对比基座 / 旧翻译 LoRA / 新 LoRA，
  量化「未要求却翻译」行为（43 → 23 条，粗规则）并人工核验，证明行为已纠偏。
- 完成 FP16 底模合并（规避 4-bit merge 的量化误差固化）与 GGUF Q4_K_M 导出（14GB → 4.4GB），
  本地 Ollama 可跑。
