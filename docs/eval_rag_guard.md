# RAG 检索守卫（部门 ACL + 无答案拒答）

> **性质声明**：两套黄金集都只测 **检索前的守卫**，不调 LLM、不连向量库、不打 embedding。判定函数与生产 `prepare_chat_rag` 相同：`should_use_rag` → 部门裁剪 → 公司/年份 scope。`low_score`（检索后阈值）不在这 20+20 题里。

| 任务 | 黄金集 | 指标 | 门禁 |
|------|--------|------|------|
| `rag_acl` | `eval/golden/rag_acl_20.json` | accuracy、false_accept_rate、leak_rate | 准确率 1.0，泄露 0 |
| `rag_refuse` | `eval/golden/rag_refuse_20.json` | accuracy、false_accept_rate | 准确率 1.0，误放行 0 |

## 1. 部门 ACL（检索层）

与 Java `DeptAcl` / mock 工具同一张表：

| 部门 | 可检索年报 |
|------|------------|
| `research` | 002594 比亚迪、601633 长城 |
| `rm` | 000333 美的、000651 格力 |
| `compliance` | 七家样本（原五家 + 300750 宁德时代、600519 茅台） |
| 未登录 `dept=None` | **不裁剪**（W7：问答可不登录） |
| 未知部门 | 只保留会话 PDF（`sess_*`） |

实现：`python-ai/app/rag/dept_scope.py` 先按部门滤 `doc_id`，再走 `filter_doc_ids_by_question`。问题点了本部门没有的公司（研究岗问美的）→ **空列表 / `no_docs`**，不再回退到剩余语料（否则会把比亚迪段落当成美的答案）。

Java BFF 把 JWT 里的部门解析后转成 `X-Regops-Dept` 再调 Python `/chat`。用户 JWT 不转发。

20 题覆盖：本部门放行、越权拒检、未登录开放检索、未知部门、库外公司不得落到本部门年报。

## 2. 无答案拒答（20 题）

| 题型 | n | 期望 |
|------|--:|------|
| `chitchat` / `off_topic` | 8 | `no_intent`（寒暄、天气） |
| `off_corpus` | 8 | `no_docs`（海康、药明、工行等，语料里没有） |
| `missing_year` | 4 | `no_docs`（比亚迪 2099、美的 2010…） |

点名了公司但语料没有对应年份时，**不再回退该司其它年份**，避免用 2024 年报回答 2099。

## 3. 怎么跑

前端：运维监控 → 评估报告，选 `rag_acl` / `rag_refuse`。

```bash
python-ai/.venv/bin/python eval/run_rag_acl.py --fail-on-regression
python-ai/.venv/bin/python eval/run_rag_refuse.py --fail-on-regression
```

报告：`eval/reports/rag_acl/<run>/`、`eval/reports/rag_refuse/<run>/`。

已入库年报的 `dept_acl` JSON 可回填：`docs/sql/w3_dept_acl.sql`（运行时过滤不依赖该列）。
