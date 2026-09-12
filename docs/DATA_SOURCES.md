# 数据来源与使用边界（w1-5）

> **性质声明**
>
> RegOps Copilot 是**个人学习作品集 / 技术演示项目**，**不是任何金融机构的生产系统**，
> 也不用于真实的合规审查、投资决策或对外提供服务。
>
> 项目使用的全部业务数据均为**已公开披露的信息**（上市公司定期报告、监管机构公开文件）。
> 项目**不包含**任何客户数据、个人隐私信息（PII）、内部未公开材料或非公开经营数据。
>
> 所有由模型生成的内容均附免责声明（见 `ChatResponse.disclaimer`），
> 不构成合规意见或投资建议。

---

## 1. 数据来源清单

### 1.1 上市公司年度报告（PDF，RAG 主语料）

| doc_id | 公司 | 代码 | 报告期 | 披露日 | 页数 | 披露渠道 |
|--------|------|------|--------|--------|------|----------|
| `002594_2024` | 比亚迪 | 002594 | 2024 年度 | 2025-03-25 | 290 | 巨潮资讯网 |
| `002594_2023` | 比亚迪 | 002594 | 2023 年度 | 2024-03-27 | 266 | 巨潮资讯网 |
| `601633_2024` | 长城汽车 | 601633 | 2024 年度 | 2025-03-29 | 330 | 巨潮资讯网 |
| `601633_2023` | 长城汽车 | 601633 | 2023 年度 | 2024-03-29 | 326 | 巨潮资讯网 |
| `000333_2024` | 美的集团 | 000333 | 2024 年度 | 2025-03-29 | 295 | 巨潮资讯网 |
| `000333_2023` | 美的集团 | 000333 | 2023 年度 | 2024-03-28 | 291 | 巨潮资讯网 |
| `000651_2024` | 格力电器 | 000651 | 2024 年度 | 2025-04-28 | 248 | 巨潮资讯网 |
| `000651_2023` | 格力电器 | 000651 | 2023 年度 | 2024-04-30 | 249 | 巨潮资讯网 |
| `600031_2024` | 三一重工 | 600031 | 2024 年度 | 2025-04-18 | 255 | 巨潮资讯网 |
| `600031_2023` | 三一重工 | 600031 | 2023 年度 | 2024-04-29 | 247 | 巨潮资讯网 |
| `300750_2024` | 宁德时代 | 300750 | 2024 年度 | 2025-03-15 | 229 | 巨潮资讯网 |
| `600519_2024` | 贵州茅台 | 600519 | 2024 年度 | 2025-04-03 | 143 | 巨潮资讯网 |

- **渠道**：巨潮资讯网（<http://www.cninfo.com.cn>），深交所/上交所指定信息披露平台。
- **性质**：上市公司依法公开披露的年度报告全文，任何人可自由查阅下载。
- **落地位置**：`data/raw/<code>_<year>_annual.pdf`（**不入版本库**，见第 3 节）。
- **获取脚本**：`python-ai/scripts/download_annual_pdfs.py`（巨潮 `hisAnnouncement` → `static.cninfo.com.cn`）。
- **入库记录**：`pdf_document` 表，`source_site = 'cninfo'`，含 `content_hash`、`page_count`、`doc_type = 'annual_report'`、`disclosure_date`（巨潮公告日，见 `app/ingest/disclosure_dates.py`）。
- **报告期 vs 披露日**：表中「报告期」是会计期间；「披露日」是巨潮全文年报公告日（如比亚迪 2024 年报于 2025-03-25 披露）。二者不可混用。
- **为什么选 2024 + 2023 年报**：2024 年报晚于 FinQA / CFLUE 等公开基准的主要构造期；
  原五家另入库 2023 年报与 F10，便于问「同比 / 近两年」（检索会同时带上当年与上一年文档）。
  宁德时代、贵州茅台目前仍只有 2024。

### 1.2 结构化财务数据（JSON，`fin_metric` 原型用）

- **来源**：东方财富 F10 公开财务报表接口（资产负债表 / 利润表 / 现金流量表）。
- **落地位置**：`data/raw/xbrl/<code>_<year>/{balance,income,cashflow}.json`，
  同目录 `manifest.json` 记录 `stock_code`、`org_id`、`exchange`、`report_year`、
  `report_date`、`downloaded_at`。
- **获取脚本**：`python-ai/scripts/download_xbrl.py`。
- **入库脚本**：`python-ai/scripts/ingest_fin_metric.py`（G1/G2/G3 后写入 `fin_metric`，`source_type=web`）。
- **为什么不是 XBRL**：A 股发行人确实按 JR/T 0021 报送 XBRL instance 文档，
  但公开渠道拿不到原始实例文件——巨潮 `hisAnnouncement/query` 只返回 PDF 附件，
  历史上承载实例文件的 `xbrl.cninfo.com.cn`、`listxbrl.sse.com.cn`、`xbrl.szse.cn`
  在本项目环境下均不可达。故降级用 F10 结构化 JSON 作为 `fin_metric` 的原型数据源，
  该结论与探测证据记录在各目录的 `manifest.json` 中。

### 1.3 监管制度与合规知识（评测集构造依据）

- **来源**：证监会、金融监管总局、人民银行等**公开发布**的监管规则与公开表述
  （如《商业银行资本管理办法》公开监管框架、反洗钱义务的公开条款表述）。
- **用途**：仅用于构造 `eval/golden/w1_chat_30.json` 中的闭卷概念题
  （监管制度 + 会计/银行/市场口径），题面为概念性提问，不摘录受版权保护的长段原文。

### 1.4 自建评测黄金集

| 文件 | 版本 | 规模 | 数据性质 |
|------|------|------|----------|
| `eval/golden/w1_chat_30.json` | `w1-v2` | 30 道闭卷金融概念题 | 题面自撰；不引用具体年报数字 |
| `eval/golden/rag_retrieval_100.json` | `rag-retrieval-v1` | 100 题 | 基于上表五份年报，标注 `doc_id` + `gold_pages` |
| `eval/golden/compliance_schema_20.json` | `compliance-schema-v1` | 10 合法 + 10 非法 | **全合成样例**，不含任何真实主体信息 |

`compliance_schema_20.json` 中的条款编号（如 `AML-12-3`、`CSRC-2024-17`）与结论文本
均为**虚构示例**，仅用于校验 Pydantic 约束，不对应任何真实监管条款。

---

## 2. 引用与溯源方式

每条评测样本都要能回答「这个答案凭什么」：

- `w1_chat_30.json`：每条带 `source_doc`（口径来源）+ `why_clean`。v2 起全部为闭卷概念题，不再绑定工行/招行/建行年报数字。
- `rag_retrieval_100.json`：每条带 `doc_id`、`gold_pages`（证据页码）、
  `company_code`、`report_year`、`evidence_hint`。
- RAG 回答：`ChatResponse.citations[]` 返回 `doc_id` + `page` + `snippet` + `viewer_url`，
  前端可跳转到原文对应页，答案不脱离出处。
- 入库文档：`pdf_document` 保留 `content_hash` 与 `source_site`，可校验文件未被替换。
- 评测报告：`app/eval/provenance.py` 记录 git commit 与黄金集文件 SHA256，
  保证「同一份报告能复现」。

### 已知溯源缺口

- 年报取数不在 `w1_chat` 范围内。问具体公司某年数字，应走 `rag_retrieval_100.json`
  （带 `doc_id` / 页码）或 W4 `fin_metric` 问数；当前入库主体是上表七家公司。
  检索 100 题黄金集仍覆盖原五家制造业年报。
- 已入库行若 `disclosure_date` 仍为空，跑一次
  `python-ai/.venv/bin/python python-ai/scripts/backfill_disclosure_dates.py`（新 ingest 会自动写入）。

---

## 3. 不做的事（使用边界）

- **不含客户数据 / PII**：项目不采集、不存储任何自然人身份信息、账户信息或交易明细。
  `compliance_schema_20.json` 中出现的「客户」均为虚构表述。
- **不含内部未公开材料**：不使用任何机构内部制度、未公开的经营数据或工作底稿。
- **不再分发第三方基准原数据**：CFLUE / FinEval / FinQA / FinanceBench / FinMTEB 等
  公开基准，仓库只提交**下载脚本与许可摘要**，不提交原始数据文件
  （规则见 `eval/scripts/README.md`）。
- **不声称机构级评测结论**：自建黄金集用于**管线回归**（改了 Prompt/检索后有没有变差），
  不用于对外的模型**能力宣称**；公开榜单分数不写入作品集结论。
- **不作为生产合规依据**：模型输出一律附免责声明，且合规结论在设计上要求
  可追溯到条款（`ComplianceConclusion.clause_refs` 至少一条）并经人工复核（W7 maker-checker）。

---

## 4. 版本库排除规则

以下内容**不进版本库**（见 `.gitignore`）：

```
.env                 # API Key
data/raw/            # 年报 PDF、F10 JSON
data/labeling/       # 标注任务与对照 PDF
data/objects/        # 本地对象存储
```

仓库中保留的是**可复现的路径**：下载脚本、黄金集 JSON、评测报告、以及
`manifest.json` 形式的溯源信息。他人克隆后按 `python-ai/scripts/download_annual_pdfs.py`、`python-ai/scripts/download_xbrl.py`
与巨潮公开页面即可自行获取同一批数据。

---

## 5. 相关文档

- API 契约与服务边界：[`api-spec.md`](./api-spec.md)
- W1 评测基线：[`eval_w1_baseline.md`](./eval_w1_baseline.md)
- RAG 检索评测：[`eval_rag_retrieval.md`](./eval_rag_retrieval.md)
- RAG 检索消融（baseline / hybrid / rerank）：[`eval_rag_ablation.md`](./eval_rag_ablation.md)
- 入库校验规则：[`INGEST_VALIDATION.md`](./INGEST_VALIDATION.md)
- 公开基准选型（不提交原数据）：[`benchmarks/README.md`](./benchmarks/README.md)
