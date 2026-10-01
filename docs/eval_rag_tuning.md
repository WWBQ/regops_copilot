# RAG 重排候选数寻优（2026-10-01）

## 结论

生产默认固定为：

- 普通 RAG：`RAG_RERANK_CANDIDATES=12`
- 多公司独立检索：`RAG_COMPARE_RERANK_CANDIDATES=12`
- 多公司每家公司最终保留：`RAG_COMPARE_TOP_K_PER_COMPANY=6`

不是凭单次问答选参数。先用 `eval/validate_rag_golden.py` 校验 100 题黄金集，结果为
100/100、0 error、0 warning；再按 9 类题型分层抽样比较质量和热启动延迟。

## 普通 RAG（18 题，top_k=12）

| 候选数 | Recall@12 | MRR | nDCG@12 | CiteAcc | P50 | P95 |
|---:|---:|---:|---:|---:|---:|---:|
| **12** | **61.11%** | **0.4182** | 0.2742 | **9.78%** | **5.0s** | **5.4s** |
| 24 | 61.11% | 0.3995 | **0.2836** | 9.19% | 10.9s | 22.6s |

24 条只让 nDCG 增加 0.0094，Recall 不变，MRR 和引用准确率下降，P95 增加约 4.2 倍。
按“质量距最优不超过 1 个百分点时选 P95 更低者”的规则，选择 12。

## 多公司单边检索代理集（12 题，top_k=6）

比较流程会按公司、年份独立过滤后分别检索，因此使用叙述性题型模拟每一侧证据检索。

| 候选数 | Recall@6 | MRR | nDCG@6 | CiteAcc | P50 | P95 |
|---:|---:|---:|---:|---:|---:|---:|
| **12** | **58.33%** | **0.4236** | **0.2774** | **18.33%** | **5.4s** | **5.7s** |
| 24 | 58.33% | 0.4167 | 0.2644 | 15.83% | 11.7s | 18.8s |

12 条四项质量指标均不差于 24，P95 约为后者 30%，所以比较场景也选 12。

## 40 / 80 冒烟

2 题冒烟中，普通 RAG 的 P50 从 12 条约 4.9s 增长到 40 条约 33.6s、80 条约
66.2s；比较代理集 40 / 80 条也达到约 61.0s / 75.6s。两档 Recall 没有增加，排序
指标反而下降，因此不再占用数小时跑全量。

## 复跑

```bash
# 黄金集结构、公司/年份、页码及关键词证据校验
python-ai/.venv/bin/python eval/validate_rag_golden.py

# 默认每类抽 2 题，扫描 12/24/40/80；完整报告写入 eval/reports/rag_tuning/
python-ai/.venv/bin/python eval/run_rag_tuning.py

# 夜间全量 100 题（耗时很长）
python-ai/.venv/bin/python eval/run_rag_tuning.py --items-per-category 0
```

原始报告位于本机 gitignore 目录：

- 普通 RAG：`eval/reports/rag_tuning/20261001_124912/report.json`
- 修正 `top_k=6` 后的比较场景：`eval/reports/rag_tuning/20261001_125626/report.json`

报告带 Git commit、黄金集 SHA256、模型和配置快照。更换语料、切分、Embedding、重排模型
或运行设备后，必须重新评测。
