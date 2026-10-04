# W6-3 数字校验黄金集（归档）

> **性质声明**：不调 LLM。对终稿里的数字做抽取 + 回溯（事实库 / 引用片段），判定放行或拦截是否符合黄金集。原始 `eval/reports/w6_number_check/` 在 gitignore；本页是可提交的对照结论。门禁：`eval/run_w6_number_check.py --fail-on-regression` 与 `python-ai/tests/test_number_check_eval.py`。

黄金集：`eval/golden/w6_number_check_20.json`（`w6-number-check-v1`，20 题）。

## 1. 指标口径

| 指标 | 含义 |
|------|------|
| **accuracy** | 放行/拦截方向，以及拦截类别（`unbacked` / `unit_error` / `percent_scale` / `computed`）符合预期 |
| **false_accept_rate** | 应拦截却放行；门禁要求为 **0** |
| **false_reject_rate** | 有证据却被拦 |
| **number_error_rate** | 抽取到的数字中无法回溯的比例（与 accuracy 分开：黄金集里本来就有一半题是故意写错/无证据的） |
| **unit_error_rate** | 含万元/亿元或百分数量纲问题的**样本**占比 |

## 2. 本次结果（2026-09-10）

| 指标 | 数值 |
|------|------|
| 样本 | 20 |
| accuracy | **100%** |
| false_accept | **0**（0%） |
| false_reject | **0**（0%） |
| number_error_rate | 50%（20 条 claim 中 10 条被拦，与「一半题该拦」一致） |
| unit_error_count | 4 |
| unit_error_rate | 20%（4/20 样本含单位或百分数量纲问题） |
| computed_count | 2 |
| unbacked_count | 4 |

按题型全部通过：

| 题型 | 样本 | 通过 |
|------|------|------|
| grounded | 5 | 5 |
| citation | 3 | 3 |
| skip_meta | 2 | 2 |
| unbacked | 3 | 3 |
| unit_error | 2 | 2 |
| percent_scale | 2 | 2 |
| computed | 2 | 2 |
| mixed | 1 | 1 |

应拦截且拦截成功的样例：`nc-011`–`nc-013` unbacked，`nc-014`–`nc-015` unit_error，`nc-016`–`nc-017` percent_scale，`nc-018`–`nc-019` computed，`nc-020` mixed（unbacked）。评测失败：无。

## 3. 怎么复跑

```bash
python-ai/.venv/bin/python eval/run_w6_number_check.py --fail-on-regression
```

`--fail-on-regression`：accuracy < 100% 或出现误放行则非零退出。JSON/Markdown 写到 `eval/reports/w6_number_check/<时间戳>/`（不入库）。

## 4. 结果说明

数字校验的价值不是「准确率 100%」好看，而是 **误放行必须为 0**：无出处的亿、万元当元、百分数量纲、手算比率，都在代码里拦，不靠 Prompt。`number_error_rate=50%` 是黄金集设计（一半题故意有问题），不要当成系统漏了一半数字。
