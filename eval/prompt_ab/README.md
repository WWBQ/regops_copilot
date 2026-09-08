# eval/prompt_ab

W8 Prompt A/B 与四策略对照的**可提交示例**。`eval/reports/` 仍 gitignore，日常跑出来的 JSON 不要当资产提交。

| 文件 | 含义 |
|---|---|
| `examples/ab_n30_delta3.md` | n=30、Δ=3.3%、credible=false |
| `examples/strategy_compare.md` | Zero-shot / Few-shot / CoT / ReAct 对照表 |

复跑：

```bash
python-ai/.venv/bin/python eval/run_w8_strategy.py
python-ai/.venv/bin/python eval/run_w8_ab.py --write-example
python-ai/.venv/bin/python eval/run_w8_prompt_pin.py list
```

口径见 [`docs/W8_PROMPTS.md`](../../docs/W8_PROMPTS.md)。
