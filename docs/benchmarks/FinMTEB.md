# FinMTEB

Tang & Yang，EMNLP 2025。[论文 arXiv:2502.10990](https://arxiv.org/abs/2502.10990) · [GitHub `yixuantt/FinMTEB`](https://github.com/yixuantt/FinMTEB) · [HF org `FinanceMTEB`](https://huggingface.co/FinanceMTEB) · [Leaderboard](https://huggingface.co/spaces/FinanceMTEB/FinanceMTEB_Leaderboard)

## 能测什么

金融域 **Embedding** 套件：64 个数据集 × 中英 × 7 类任务（分类、聚类、检索、句对分类、重排、摘要、STS）。用来回答「通用向量模型在金融文本上够不够」，不是用来回答年报问题。

论文里三条和本项目直接相关的结论：

1. 金融域适配后的向量模型显著好于通用模型。
2. **通用 MTEB 分数预测不了金融任务分数。**
3. 金融 STS 上，词袋模型反而能超过一众 dense embedding——说明金融套话（风险提示、标准化表述）会让向量相似度失真。

本仓库 W3 用的是 `BAAI/bge-m3`（1024 维）+ `bge-reranker-v2-m3`。FinMTEB 解释了「为什么要看金融检索集、不能只看通用 MTEB」。

## 不能测什么

- 端到端 RAG 正确率、引用页码、拒答。
- 中文 A 股年报这一份语料上的 Recall@k——64 集里大部分不是巨潮年报。
- 生成质量（chat / Agent）。

笔记里的 FiQA-SA、FPB、Headlines、FinRED、ECTSum 等，许多是 FinMTEB 的**子任务**，不要再各写一张卡。

## 语言 / 文档类型

中英都有。短句、标题、研报片段、检索 query-doc 对。不是 300 页 PDF。

## 许可

评测框架基于 MTEB；GitHub 仓库未见单独 LICENSE 文件。**64 个子数据集各自保留原许可**——有的可商用，有的 NC。使用某一子集前必须打开该集在 Hugging Face 上的 `license` 字段。本项目**不下载、不 redistributing 这 64 集**；只引用论文结论。

配套模型 Fin-E5 是作者在金融数据上微调的 e5-Mistral，和本仓库的 bge-m3 不是同一个东西，选型时不要混。

## 污染风险

对 **Embedding 选型**污染不致命：评测的是向量空间，不是「背答案」。对 **生成模型** 无直接意义。子数据集里不少 2018–2022 的金融 NLP 集，生成模型可能见过原文，但不改变「bge-m3 要不要换」这个问题的实验设计。

## 推荐用途

**W3 Embedding 选型时读论文、看 leaderboard，不要全量复跑 64 集。** 本项目的检索门禁是 `rag_retrieval` 的 page Recall@k / MRR。若以后对比 bge-m3 vs 金融微调向量，只挑 FinMTEB 的 **Retrieval / Reranking** 中英各 1–2 个子集，结果留在 `eval/.cache/`，不写进对外能力数字。
