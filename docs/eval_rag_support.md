# RAG 引用片段撑住答案（20 题）

> 和 [`eval_rag_retrieval.md`](./eval_rag_retrieval.md) 的页级 Recall **分开报**。79% 只说明「标准答案页有没有进 top-12」；这套题问「进了的片段里，答题要用的词在不在」。

不调 LLM。检索仍走生产路径，看 `must_contain` 是否都出现在返回正文里。

第一次生产路径（同页上限 2）：**support_hit_rate 55%** / **support_coverage 60%**（`eval/reports/rag_support/20260911_235731/`）。页级 Recall 79% 时，列举细节和表格里的精确金额仍经常不在返回的那几段里。

| 指标 | 含义 |
|------|------|
| **support_hit_rate** | 20 题里「必须出现的词全部找到」的比例 |
| **support_coverage** | 每题找到的必须词占比，再平均 |

```bash
python-ai/.venv/bin/python eval/run_rag_support.py
```

黄金集：`eval/golden/rag_support_20.json`。证据词从入库年报正文抽检，不是模型生成的答案。

---

*版本 rag-support-v1 · 2026-09-11*
