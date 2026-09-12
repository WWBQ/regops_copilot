# eval/scripts

本目录用于存放 **公开 benchmark 的下载脚本与许可说明**（Day 6 w1-6）。

**规则：**

- 只提交脚本、README、许可摘要
- **不要** commit CFLUE / FinEval / FinQA 等原数据文件
- 若自行下载，放到 `eval/.cache/benchmarks/`（已 gitignore）

公开基准入口（只打印 URL + 许可，不下数据）：

```bash
eval/scripts/download_cflue.sh
eval/scripts/download_fineval.sh
eval/scripts/download_finqa.sh          # FinQA + TAT-QA
eval/scripts/download_financebench.sh
eval/scripts/download_finmteb.sh
```

选型卡：[`docs/benchmarks/`](../../docs/benchmarks/README.md)

RAG 检索集生成（默认只出 diff）：`python-ai/.venv/bin/python eval/scripts/build_rag_retrieval_golden.py --dry-run`

覆盖写入须显式 `--write`。

RAG 引用片段撑住答案（20 题，不和 Recall 混报）：`python-ai/.venv/bin/python eval/run_rag_support.py`

RAG 检索消融（baseline / hybrid / rerank）：`python-ai/.venv/bin/python eval/run_rag_ablation.py`

RAG 部门 ACL / 无答案拒答：`python-ai/.venv/bin/python eval/run_rag_acl.py --fail-on-regression`；
`python-ai/.venv/bin/python eval/run_rag_refuse.py --fail-on-regression`

合规 Schema 校验集生成：`python-ai/.venv/bin/python eval/scripts/build_compliance_schema_golden.py`

W4 问数黄金集评测：`python-ai/.venv/bin/python eval/run_asknum.py --fail-on-regression`
（长度边界样例需字符级精确，故用脚本生成而非手写 JSON）

W6 数字校验：`python-ai/.venv/bin/python eval/run_w6_number_check.py --fail-on-regression`
（归档说明 [`docs/eval_w6_number_check.md`](../../docs/eval_w6_number_check.md)）

W8 Prompt 黄金集生成：`python-ai/.venv/bin/python eval/scripts/build_w8_prompt_golden.py`

W8 四策略对照：`python-ai/.venv/bin/python eval/run_w8_strategy.py`

W8 Prompt A/B：`python-ai/.venv/bin/python eval/run_w8_ab.py --write-example`

Prompt 钉扎/回滚：`python-ai/.venv/bin/python eval/run_w8_prompt_pin.py list`

W9-1 双栈五条链路冒烟：`python-ai/.venv/bin/python eval/run_w9_e2e.py`

W9-2 金融红队：`python-ai/.venv/bin/python eval/run_w9_redteam.py --fail-on-regression`

W9-4 Compose 冒烟：`./scripts/compose-smoke.sh`

DeepSeek / Qwen 选型对照：`python-ai/.venv/bin/python eval/scripts/run_model_selection.py`
（写 `eval/reports/model_selection_w1/raw.json`，结论见 `docs/model_selection_w1.md`）
