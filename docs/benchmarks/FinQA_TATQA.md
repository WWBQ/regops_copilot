# FinQA / TAT-QA

同一张卡：都是「表格 + 周围文字 → 算出一个数」，对照 **W3 年报检索 / W4 问数** 的形态，不是对照语料，也不是 w1-4 闭卷概念题。

| | FinQA | TAT-QA |
|--|-------|--------|
| 论文 | Chen et al., EMNLP 2021 | Zhu et al., ACL 2021 |
| 规模 | 约 8k QA，约 2.8k 份财报片段 | 16,552 QA，2,757 个「表+文」上下文，来自 182 份报告 |
| 代码 | [czyssrs/FinQA](https://github.com/czyssrs/FinQA) MIT | [NExTplusplus/TAT-QA](https://github.com/NExTplusplus/TAT-QA) MIT |
| 数据许可 | 项目页写 **CC BY 4.0**；代码 MIT | **CC BY 4.0** |
| 入口 | [finqasite.github.io](https://finqasite.github.io/) · [ibm-research/finqa](https://huggingface.co/datasets/ibm-research/finqa) | [HF next-tat/TAT-QA](https://huggingface.co/datasets/next-tat/TAT-QA) |
| 金标准 | 可执行推理程序 + 支撑句 | 答案、推导过程、scale |

ConvFinQA（对话式多步 FinQA）是后续工作，需要时再看，不单独立卡。

## 能测什么

- 在**给定表和前后文**里做加减乘除、比较、计数。
- 答案是否可复现（FinQA 的 program / TAT-QA 的 derivation）。
- 模型是「读表」还是「背数字」。

本项目里对应的是带 `doc_id` / 页码的检索集（`rag_retrieval_100.json`）以及以后的 `fin_metric` 问数，不是 `w1_chat`。

## 不能测什么

- **检索**：上下文已经喂好，没有「先从 300 页里找到那张表」。
- 中文披露口径（营业收入 vs 营业总收入、合并 vs 母公司）。
- 本项目入库的五家制造业公司——FinQA/TAT-QA 是英文美股/国际报告。
- 因此**不能**用 FinQA 准确率代替 `w1_chat` 闭卷概念准确率，也不能代替 RAG 的 page 命中。

## 语言 / 文档类型

英文。表 + 短段落，不是整本 PDF + 页码。TAT-QA 每个上下文至少一张表和两段说明文字。

## 许可

两者数据均为 **CC BY 4.0**（可商用，须署名），代码采用 MIT；**原始数据仍不提交到本仓库**。

## 污染风险

**很高。** 2021 年发表，是金融 NLP 最常用的训练/评测集之一。闭源和开源模型都可能背过题。自建年报检索题用 2024 年报（2025 年披露）就是为了躲开这层污染——见 `eval_rag_retrieval.md`。

## 推荐用途

**理解带证据的数字题该长什么样、金标准为什么要带推导。** 不跑官方榜，不把分数写入能力宣称。日常回归：闭卷概念用 `w1_chat_30.json`；读表/找页用 `rag_retrieval_100.json`；终稿数字能否回溯用 `w6_number_check_20.json`（量纲错误、手算差额、无证据编造是 FinQA 常见失败形态，但题面是本仓库自建中文样例，不是 FinQA 原题）。
