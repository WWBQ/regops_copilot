# RAG 检索评测黄金集（100 条）

> **性质声明**：基于已入库 5 份 2024 年报构造，用于 RegOps Copilot 检索管线回归，gold page 由 `doc_chunks` 关键词探测 + 人工 override 生成，请对照 PDF 抽检。

## 1. 文件

| 文件 | 说明 |
|------|------|
| `eval/golden/rag_retrieval_100.json` | 100 条检索题，含 `gold_pages` |
| `eval/scripts/build_rag_retrieval_golden.py` | 从 DB 重新探测并生成 JSON |
| `eval/run_rag_retrieval.py` | 跑 Recall@k / MRR 并输出报告 |

## 2. 覆盖范围

**语料（5 家，各 20 题）：**

| doc_id | 公司 |
|--------|------|
| `002594_2024` | 比亚迪 |
| `601633_2024` | 长城汽车 |
| `000333_2024` | 美的集团 |
| `000651_2024` | 格力电器 |
| `600031_2024` | 三一重工 |

**题型（每类 10 题，可重复出现在不同公司）：**

| category | 说明 | 示例 |
|----------|------|------|
| `numeric_financial` | 财务数字直读 | 营业收入、净利润、研发投入 |
| `numeric_ratio` | 比率/指标 | 毛利率、ROE、资产负债率 |
| `product_enum` | 产品/车型列举 | 2024 新推出车型、新品发布 |
| `segment_business` | 分部/区域/业务线 | 海外销售、分产品收入 |
| `compliance_risk` | 合规与风险 | 内控评价、风险因素、审计 |
| `governance` | 治理与股东 | 分红方案、董事、回购 |
| `esg_sustainability` | ESG/低碳 | 碳排放、绿色制造、社会责任 |
| `strategy_outlook` | 战略与展望 | 新能源战略、全球化、数字化 |
| `cross_year_compare` | 同比/变动 | 营收同比增长、海外销售增长 |

## 3. 单条 JSON 字段

```json
{
  "id": "rag-001",
  "category": "numeric_financial",
  "question": "比亚迪2024年营业收入是多少",
  "doc_id": "002594_2024",
  "company_code": "002594",
  "company_name": "比亚迪",
  "report_year": 2024,
  "gold_pages": [11, 10],
  "probe_keywords": ["营业收入", "营业总收入"],
  "grading": "page_hit_at_k",
  "k": 12,
  "evidence_hint": "主要会计数据",
  "why_clean": "..."
}
```

- **gold_pages**：可接受证据页列表，命中任一即算 Recall@k 成功
- **k**：默认 12，与 `rag_top_k` 对齐

## 4. 怎么跑

### 前端（推荐）

打开 **运维监控 → 评估报告**（`/ops/eval`）：

1. 下拉选择评测任务（W1 聊天 / RAG 检索）
2. 点击 **运行评测**
3. 等待进度条完成，右侧查看汇总与明细
4. 左侧历史列表可切换查看不同 run 的报告

### 上传黄金集（数据集）

**前端（推荐）：** 评估报告 → **管理任务** → 选择 JSON 文件 → **上传数据集**

**格式要求：**

```json
{
  "version": "my-v1",
  "items": [
    {
      "id": "q-001",
      "category": "numeric_financial",
      "question": "比亚迪2024年研发投入是多少",
      "doc_id": "002594_2024",
      "gold_pages": [3, 14],
      "grading": "page_hit_at_k",
      "k": 12
    }
  ]
}
```

RAG 检索集每题必须有 `question`、`doc_id`、`gold_pages`。上传后在下拉框选该文件，再**添加任务**。

**API：** `POST /api/ops/eval/golden-sets/upload`

### 添加自定义任务

1. 将黄金集 JSON 放入 `eval/golden/`（格式同现有文件）
2. 前端 **管理任务** → 填写任务 ID、名称、选择黄金集与 runner → **添加任务**
3. 或直接编辑 `eval/tasks.json` 后刷新页面

### 删除

| 对象 | 规则 |
|------|------|
| **任务** | 仅自定义任务可删；内置 `w1_chat` / `rag_retrieval` 不可删 |
| **历史报告** | 运行中的不可删；删除后 `eval/reports/{task_id}/{run_id}/` 目录移除 |

### CLI

```bash
cd /Users/chengfeng/Desktop/AI/regops_copilot
python eval/run_rag_retrieval.py

# 调试
python eval/run_rag_retrieval.py --limit 5
python eval/run_rag_retrieval.py --category product_enum
```

报告目录：`eval/reports/{task_id}/{run_id}/report.json`

## 5. 指标

| 指标 | 定义 |
|------|------|
| **Recall@k** | top-k 检索结果页码中，是否出现任一 `gold_pages` |
| **MRR** | 第一个 gold page 出现位次的倒数均值 |

## 6. 重新生成 gold page

入库或 re-ingest 后若 chunk 页码变化，可重跑：

```bash
cd python-ai && .venv/bin/python ../eval/scripts/build_rag_retrieval_golden.py
```

手工修正：编辑 `MANUAL_GOLD_PAGES`（`build_rag_retrieval_golden.py`）后重新生成。

---

*版本 rag-retrieval-v1 · 2026-08-21*
