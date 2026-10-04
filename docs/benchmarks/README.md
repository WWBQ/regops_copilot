# 金融基准选型（w1-6）

五张卡回答同一件事：**这个榜能不能信、对本项目能干什么。**
不是再造一套评测跑数，也不把公开分数写进项目结论。

| 卡 | 基准 | 对本项目 | 推荐用途 |
|----|------|----------|----------|
| [CFLUE.md](./CFLUE.md) | 中文金融知识 + 应用 NLP | 对照 w1-1 概念题、模型选型 | 题型参考；**不作能力宣称** |
| [FinEval.md](./FinEval.md) | 中文金融综合考题 | 同上，覆盖面更像「从业资格」 | 题型参考；**不作能力宣称** |
| [FinQA_TATQA.md](./FinQA_TATQA.md) | 英文财报表格+文本数字推理 | 对照 W3 检索 / W4 问数形态，不是 w1-4 闭卷概念题 | 理解「数字要从表里算」；**不替代自建集** |
| [FinanceBench.md](./FinanceBench.md) | 英文 10-K 开卷金融 QA | 最接近 W3 年报 RAG | 题型/失败模式参考；公开只有 150 条 |
| [FinMTEB.md](./FinMTEB.md) | 金融 Embedding 64 集 | 对照 W3 Embedding 选型 | 看论文结论即可；不必全量复跑 |

获取方式（只打印官方链接与许可，**不把原数据提交进仓库**）：

```bash
eval/scripts/download_cflue.sh
eval/scripts/download_fineval.sh
eval/scripts/download_finqa.sh
eval/scripts/download_financebench.sh
eval/scripts/download_finmteb.sh
```

落地目录约定：`eval/.cache/benchmarks/`（已加入 `.gitignore`）。

## 和自建集怎么分工

| | 公开基准 | 自建黄金集 |
|--|----------|------------|
| 用来干什么 | 理解题型、看别人怎么标注、W3 对标 Embedding | **改 Prompt / 检索之后有没有变差** |
| 污染 | 2021–2024 发表，主流模型很可能见过 | 2024 年报 2025 年才披露；合规 Schema 为全合成 |
| 语言 / 文档 | 多为英文 10-K 或中文考题 | A 股年报 PDF + 中文监管表述 |
| 对外结论 | 只说明采用的公开协议 | 只采用可复现报告中的 accuracy / 误放行率，不编造相对公开榜的提升百分比 |

## 故意不写卡的

笔记里另外几十个名字不逐张开卡：

- **预训练语料**（SEFD、IndustryCorpus2、CFData-pt、2TB 金融语料、Bean Counter）：用来继续训模型，本项目不入库。
- **刷榜套件**（FinBen/PIXIU、FLARE、Open FinLLM Leaderboard）：把上面那些集打包跑，不是独立基准。
- **情感 / NER / 信贷表**（FPB、FiQA-SA、Lending Club、ccfraud…）：不是合规问答或年报 RAG。
- **Agent / 交易**（FinAgentBench、FinTrade）：W5 以后再说。

## 选型验收

1. **公开基准和自建 30 条怎么分工？**  
   公开基准看题型和标注方式；日常回归和防污染用自建近期披露集。CFLUE 刷高了说明模型会做中文金融选择题，说明不了「能从比亚迪 2024 年报第几页把营收找对」。

2. **FinanceBench 分数能否作为本项目能力数字？**
   不能。公开只有 150 条、英文 10-K、CC-BY-NC，全文 1 万条不开放。本项目只记录已复现的页码引用和拒答结果，不声明超过未复跑的公开基线。
