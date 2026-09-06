# W1 聊天评测基线（w1-4）

> **性质声明**：本黄金集基于公开监管知识与公开金融教材口径构造，用于测试**原生模型闭卷能力**，不构成任何机构评测结论。年报数字提取不在本集范围内。

## 1. 这套集测什么

30 道全部是闭卷概念题，发给 `/chat` 时固定 `use_rag=false`。没有文档也能答——答的是参数里的金融知识，不是某家公司某年的报表。

| 类型 | 大约数量 | 说明 |
|------|----------|------|
| `clause` | 15 | 监管制度、合规概念（资本充足率层次、反洗钱义务、穿透式监管等） |
| `accounting` | 4 | 报表口径与财务比率（营收 vs 营业利润、权责发生制、商誉、ROE/ROA） |
| `banking` / `macro` | 4 | 五级分类、净息差、准备金率、再贷款 vs 再贴现 |
| `market` / `securities` / `credit` | 7 | 估值、久期、内幕信息、一致行动人、做市商、违约处置、系统性风险 |

文件：`eval/golden/w1_chat_30.json`（版本 `w1-v2`）

**为什么删掉数字题？** 问「工行 2024 归母净利是多少」而库里没有该年报，测的是会不会瞎编，不是金融能力。那种题属于 W3 RAG / W4 问数，金标准必须带 `doc_id` 和页码。

## 2. 与公开 benchmark 的分工

| 用途 | 用什么 |
|------|--------|
| **日常改模型/Prompt 后的回归** | 本黄金集 + `eval/run_w1_chat.py`（关 RAG） |
| **理解题型与标注方式** | CFLUE / FinEval（选择题知识）见 [`docs/benchmarks/`](./benchmarks/README.md) |
| **年报数字 / 检索** | `rag_retrieval_100.json`，不是本集 |
| **对外能力宣称** | 仍不以本集或公开榜分数对外宣称 |

## 3. 怎么跑

```bash
cd /Users/chengfeng/Desktop/AI/regops_copilot
python-ai/.venv/bin/python eval/run_w1_chat.py --base-url http://localhost:8000 --model deepseek
python-ai/.venv/bin/python eval/run_w1_chat.py --base-url http://localhost:8000 --model qwen

# 调试：只跑 3 题
python-ai/.venv/bin/python eval/run_w1_chat.py --limit 3 --model deepseek
```

页面：`/ops/eval` 选「W1 聊天评测」，选模型后运行。两份报告（例如 DeepSeek 与通义千问各一轮）可在「对比两份报告」里对照准确率、拒答率和逐题对错。`--model` 为空则用服务 `DEFAULT_MODEL`。

报告：`eval/reports/w1_chat/<时间戳>/report.json`

## 4. 判分规则

| grading | 规则 |
|---------|------|
| `contains` | `expected` 用 `\|` 分隔关键词，命中至少一半算过 |

不再使用 `numeric_tolerance`。汇总指标：`accuracy`、`refuse_rate`、`latency_p50_ms`，以及按 `category` 的准确率。

拒答（短回复且含「无法/不能/抱歉」等）单独计入 `refuse_rate`，不算作答对。闭卷概念题上，高频拒答说明模型过保守或系统提示在挡题。

## 5. 后续扩展

| 周次 | 黄金集 |
|------|--------|
| W3 | RAG 检索 `rag_retrieval_100.json`（带 evidence 页码） |
| W4 | 受控问数（`eval/golden/w4_asknum_20.json`，`lookup_metric`） |
| W6 | Agent 轨迹 |

## 6. 你可以改什么

- 替换题目时保持 `id` 稳定，便于跨版本 diff
- 制度题过严：减少 `expected` 关键词
- 不要把具体年报数字加回来，除非同时提供可检索文档并改 runner 的 `use_rag`

---

*版本 w1-v2*
