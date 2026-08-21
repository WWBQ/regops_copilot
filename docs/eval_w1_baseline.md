# W1 聊天评测基线（w1-4）

> **性质声明**：本黄金集基于公开披露信息与公开监管知识构造，用于 RegOps Copilot 学习项目的管线回归，不构成任何机构评测结论。

## 1. 这套集测什么

| 类型 | 数量 | 说明 |
|------|------|------|
| `clause` | 15 | 制度/监管/合规概念理解 |
| `number` | 15 | 2024 年报数字直读（工行/招行/建行，2025 年披露） |

文件：`eval/golden/w1_chat_30.json`

## 2. 与公开 benchmark 的分工

| 用途 | 用什么 |
|------|--------|
| **日常改模型/Prompt 后的回归** | 本黄金集 + `eval/run_w1_chat.py` |
| **理解题型与标注方式** | CFLUE / FinEval / FinQA / FinanceBench / FinMTEB（见 Day 6 选型卡） |
| **对外能力宣称** | 仍以自建留出集为主，不单靠公开榜分数 |

**为什么数字题选 2024 年报？** FinQA 等集主要截止较早年度，2024 年报在 2025 年披露，降低「模型训练时见过原题」的风险。

## 3. 怎么跑

```bash
# 终端 1：启动服务
cd python-ai && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 终端 2：跑评测（需 httpx，python-ai 环境已有）
cd /Users/chengfeng/Desktop/AI/regops_copilot
python eval/run_w1_chat.py --base-url http://localhost:8000

# 调试：只跑 3 题
python eval/run_w1_chat.py --limit 3
```

报告输出：`eval/reports/YYYYMMDD_HHMMSS/report.json` 与 `report.md`

## 4. 判分规则

| grading | 规则 |
|---------|------|
| `contains` | 期望字段用 `\|` 分隔多个关键词，命中至少一半算过 |
| `numeric_tolerance` | 从回复中提取数字，与 `expected` 比较差值 ≤ 容差 |

**说明**：W1 未接 RAG，数字题依赖模型 parametric 知识，**准确率低是正常现象**——这正是基线的价值：后续接 RAG/问数后对比是否改善。

## 5. 后续扩展

| 周次 | 新增黄金集 |
|------|------------|
| W2–W3 | RAG 检索集 80–100 条（带 evidence doc/page） → **`eval/golden/rag_retrieval_100.json`** |
| W4 | Text2SQL 问数 30 条 |
| W6 | Agent 轨迹 20 条 |

## 6. 你可以改什么

- 替换/增删题目：保持 `id` 稳定，便于 diff 报告
- 调 `numeric_tolerance`：数字题单位搞不清时可先放宽
- 制度题过严：改 `expected` 关键词或改为 `contains` 更少的词

---

*版本 w1-v1 · 脚手架生成，数字题请对照巨潮原文抽检*
