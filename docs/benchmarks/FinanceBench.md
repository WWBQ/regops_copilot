# FinanceBench

Patronus AI，2023。[论文 arXiv:2311.11944](https://arxiv.org/abs/2311.11944) · [GitHub `patronus-ai/financebench`](https://github.com/patronus-ai/financebench) · [HF `PatronusAI/financebench`](https://huggingface.co/datasets/PatronusAI/financebench)（`license: cc-by-nc-4.0`）

## 能测什么

开卷金融 QA：给定上市公司公开文件（10-K / 10-Q / 8-K / 业绩材料），回答指标、业务、新颖问题。全量号称 **10,231** 条；论文里人工复审的是 **150** 条开源样本（16 种模型配置 × 150 = 2,400 次人工看答案）。

开源字段对 RAG 很有用：`evidence_page_num`（0-based）、`evidence_text`、`doc_name`、`question_type`。失败结论也有用：当时 GPT-4-Turbo + 检索在 150 条上错误或拒答约 **81%**——说明「接了向量库」远远不够。

这是五张卡里**形态上最接近**本项目 W3 年报 RAG 的。

## 不能测什么

- **A 股 / 中文年报。** 全是美股英文披露。
- 全量 1 万条：不开放，需邮件 `contact@patronus.ai`。开源只有 150 条，**不能**代表全量分布。
- 合规条款追溯、maker-checker、中文监管口径。
- 把论文里的 81% 直接当成 2026 年 SOTA——模型已经换代，数字只说明「当时检索式金融 QA 很难」。

## 语言 / 文档类型

英文。长 PDF，页级证据。文档 ID 形如 `{COMPANY}_{PERIOD}_{TYPE}`。

## 许可

Hugging Face 与数据集卡标明 **CC BY-NC-4.0**：**非商业**。可以用于内部研究并引用论文数字；不能把 150 条或 PDF 再分发进商业产品，也不能把原数据提交到本仓库。全文 1 万条的授权以 Patronus 书面回复为准，本项目不申请。

## 污染风险

**中高。** 150 条开源 + 论文已在网上传播两年；题目对应的 10-K 本身是模型预训练常见语料。证据页码降低了「纯背答案」的可能，但公司名 + 指标仍可能被记住。本项目用五家 A 股 2024 年报做 `rag_retrieval_100.json`，就是为了不跟这 150 条撞车。

## 推荐用途

**题型与失败模式参考，不是能力宣称。** 项目结论只描述已复现的开卷设定、页级证据和拒答结果，不声明未实际运行的 FinanceBench 准确率，也不声称超过论文基线。

日常回归用 `eval/golden/rag_retrieval_100.json`，不要用这 150 条当门禁。
