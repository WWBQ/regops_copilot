# W8-2 Prompt 四策略对照

- 黄金集：w8_prompt_30.json（w8-prompt-v1）
- backend：fixture（组装真实 Prompt，不调 LLM）
- 种子：42，样本 n=30

| 策略 | 准确率 | 数字错误率 | 均 Token | P50 延迟 |
|---|---:|---:|---:|---:|
| Zero-shot | 76.7% | 3.3% | 76 | 196 ms |
| Few-shot | 96.7% | 0.0% | 188 | 286 ms |
| CoT | 56.7% | 36.7% | 110 | 516 ms |
| ReAct | 43.3% | 40.0% | 219 | 966 ms |

## 策略取舍

- **react** · 闭卷概念、没有真实工具可调：Token 和延迟明显高于 Zero-shot，准确率不升，数字错误率更高。生产继续用 W6 DAG，不上开放 ReAct。
- **cot** · 诱导手算或库外具体金额：推理链容易补出比率/金额。数字边界仍是 evidence.py，不靠 CoT Prompt。
- **few_shot** · 已经会拒答的未入库数字题：示例拉长 Prompt，拒答不再提高，Token 不值得。Few-shot 留给格式/术语题。
- **few_shot** · 闭卷监管/会计术语、需要固定表述：相对 Zero-shot 提升明显，这是 Few-shot 值得用的地方。

> 数字错误由 `evidence.py` 对 fixture 终稿打分，不把 Prompt 当控制手段。
