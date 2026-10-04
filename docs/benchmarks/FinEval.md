# FinEval

上海财经大学 SUFE-AIFLM-Lab。[论文 arXiv:2308.09975](https://arxiv.org/abs/2308.09975) · [GitHub](https://github.com/SUFE-AIFLM-Lab/FinEval) · [文档](https://fineval.readthedocs.io/) · [HF `SUFE-AIFLM-Lab/FinEval`](https://huggingface.co/datasets/SUFE-AIFLM-Lab/FinEval)

## 能测什么

2023 论文版：4,661 道高质量中文选择题，34 个学科，覆盖金融、经济、会计、从业资格。dev / val / **test 标签不公开**（交 `submission.json` 上榜）。评测协议含 zero-shot、few-shot、CoT。

GitHub 后续把套件扩到「两万六千+」题型，并加上金融安全、智能体、多模态等——那是**另一代产品形态**，和论文数字不要混着引用。本卡以论文版 + HF 可下载的选择题为主体。

和 CFLUE 的差别：FinEval 更像「从业资格模拟卷」；CFLUE 还带应用 NLP。对本项目两者都只当中文金融知识的外部镜子。

## 不能测什么

- 指定公司年报的数字提取与引用。
- 检索质量（无 `doc_id` / 页码金标准）。
- 金融智能体、K 线图、多模态——即使新版套件有，也不是 W1–W4 的任务。

test 无公开标签，本地无法复现官方榜，只能使用 val 进行内部验证。

## 语言 / 文档类型

中文（部分英文对照评测出现在论文里）。短题面，不是年报 PDF。

## 许可

评测**代码**仓库为 **Apache-2.0**。数据集经 Hugging Face 分发（`FinEval.zip`）；使用须保留论文引用。test 集答案不随下载提供，不存在「下下来自己打官方分」这条路。

不要把 zip 提交进 git。

## 污染风险

**高。** 2023 年发布，模拟考题来源公开，中文金融模型的常规训练语料高度重叠。GPT-4 在论文里约 60%——这个数字 2026 年已过时，且与 A 股 RAG 无关。

## 推荐用途

**题型参考。** 构造概念题时可以对照「资本 / 会计 / 法规」科目是否覆盖；不把 FinEval 准确率写入项目能力声明。日常回归仍用 `eval/golden/w1_chat_30.json`。
