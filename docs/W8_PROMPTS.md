# W8 Prompt 资产（模板库 · 三策略对照 · A/B）

> 目标：Prompt 可版本化、可 A/B。Dify 只做独立对照。

## 怎么走

```text
改模板
  → 新版本号 + changelog（必须绑 eval_task 或 eval_report）
  → 钉扎 pins.json（生产默认仍是 1.0.0）
  → 跑 w8_strategy / w8_ab / 既有黄金集
  → 要撤回：rollback 到任一已有版本（只改钉扎，不删正文）
```

System 和 User 分文件字段。用户问题只进 User 槽，不会拼进 System。`{question}` 这类变量只替换已声明的名字。

生产路径现已从库里读，不再在业务代码里写死长字符串：

| 模板 | 谁用 | 当前钉扎 |
|---|---|---|
| `chat.general` | `/chat` 寒暄/闭卷 | 1.0.0（与抽出前逐字相同） |
| `rag.answer` | RAG 成稿 | 1.0.0 |
| `strategy.*` | 只给 W8 评测 | 1.0.0；`zero_shot@1.1.0` 仅 A/B |

回滚：

```bash
python-ai/.venv/bin/python eval/run_w8_prompt_pin.py list
python-ai/.venv/bin/python eval/run_w8_prompt_pin.py changelog --name chat.general
python-ai/.venv/bin/python eval/run_w8_prompt_pin.py rollback --name chat.general --version 1.0.0
```

`GET /ops/prompts`、`POST /ops/prompts/{name}/rollback` 同样只改钉扎。

## 三策略对照（w8-2）

同一批 30 题：`eval/golden/w8_prompt_30.json`。题型覆盖闭卷概念、未入库数字、诱导手算、注入拒答和指定格式。Few-shot 示例是存款准备金率等**题外**样例，不抄黄金集原题。

默认 **fixture**：组装真实模板，用题面标注的 `strategy_outcomes` 生成终稿，再交给 `evidence.py` 抽数字。pytest 和 CI 不调 LLM。这不是「线上 30 题准确率」，是策略失败形态对照。

```bash
python-ai/.venv/bin/python eval/run_w8_strategy.py
```

种子 42 的一份对照（可复跑）：

| 策略 | 准确率 | 数字错误率 | 均 Token | P50 延迟 |
|---|---:|---:|---:|---:|
| Zero-shot | 76.7% | 3.3% | 76 | 196 ms |
| Few-shot | 96.7% | 0.0% | 188 | 286 ms |
| CoT | 56.7% | 36.7% | 110 | 516 ms |

**何时不值得用**

- **CoT**：诱导手算或库外金额。推理链补比率，数字错误率升到三成以上。数字边界仍是 `evidence.py`。
- **Few-shot**：未入库数字题上 Zero-shot 已经会拒，再贴示例只烧 Token。留给术语/格式题。

完整报告：[`eval/prompt_ab/examples/strategy_compare.md`](../eval/prompt_ab/examples/strategy_compare.md)。

## A/B 口径（w8-3）

同一 30 题，A=`strategy.zero_shot@1.0.0`，B=`@1.1.0`。固定种子，先打乱顺序，配对仍按题号。统计：

- 各臂 Wilson 95% 区间
- 差值 Wald 区间
- 配对 McNemar 精确 p（n01 / n10）
- `credible`：n≥100 且区间不穿过 0 且 p<0.05 且 |Δ|≥8pp，否则不算

种子 42 的结果：A 70.0%、B 73.3%、Δ=3.3%、区间 [-19.5%, 26.1%] 穿过 0、McNemar p=1.0（只有 `w8-011` 一题 B 多对）、**credible=false**。

结论原句：**n=30 提升 3% 通常不可信，不能凭这一点上线。**

```bash
python-ai/.venv/bin/python eval/run_w8_ab.py --write-example
```

## 不做什么

- 不把「不要编造」写进 Prompt 当数字门禁
- 不把 fixture 准确率写成机构级模型榜
- 不做 Langfuse（W9）
- 不把 Dify 嵌进 `/chat` 或根 `compose.yaml`

## Dify 对照（w8-4）

独立编排：[`dify/README.md`](../dify/README.md) · `./scripts/dify-up.sh`（控制台 :1380）。同一批 `data/raw/*_2024_annual.pdf` 进知识库；只搭 RAG Chatbot + 两步 Workflow。

```bash
export DIFY_APP_KEY=app-...
python-ai/.venv/bin/python eval/run_w8_dify_compare.py --write-example
```

没起来就跳过。选型表与 q67：[`dify-comparison.md`](./dify-comparison.md)。
