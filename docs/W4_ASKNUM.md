# W4 问数（第一刀）

> 受控查 `fin_metric`，不生成 SQL。设计对照见面试笔记 Q37–Q39。

## 行为

`POST /chat` 且 `use_rag=true` 时，先走 `app/asknum/`：

1. 抽出公司 + 标准 concept（营收 / 净利润 / 总资产等），且不是「为什么 / 风险 / 战略」叙述题 → 问数。
2. 缺公司 → `route=metric_clarify`，反问，不回落 RAG。
3. 命中 `status=auto_accepted` → 模板答数 + `[1]` 引用（`route=metric`），**不调 LLM（0 token）**。
4. `human_review` / 无记录 / 多值冲突 → 明说不返回数字（`route=metric_blocked`）。
5. 同比 / 季度 / ROE / 毛利率先查组成科目，缺了就说「数据不完整，不能给出」，不直接拒、不回落 RAG。
6. 抽不出 concept、但有公司且像在问数 → `metric_clarify`。叙述题（为什么 / 怎么样）才交给 Hybrid RAG。
7. `use_rag=false`（W1 评测）不拦截。

未指定年份默认 **2024**；「今年 / 本年」锚在默认报告期，**「去年 / 上年」= 2023**（库里没有就 `metric_blocked`，不估数）。口径默认 **合并报表**（问「母公司」则 `parent`）。两家公司或两个指标会逐条 `lookup_metric`，不手算比率。

抽槽：`asknum_alias` 把近义词收成标准指标或证券代码（赚了多少钱→净利润，格力股份→000651）→ 查 `fin_metric` → 抽不全就反问，查到缺组成科目就说数据不完整。表读不到时回退代码内置词。不调模型补槽。

新库由 compose 挂载 `docs/sql/w4_asknum_alias.sql`。已有库需执行一次：

```bash
docker compose exec -T db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/06_asknum_alias.sql
```

金额旁带与 RAG 相同的 `[1]` 角标：默认打开财务事实库（`/quality/facts?company_code=&concept=`）；`page_no` 有值或年报 chunk 能**唯一**对上科目+金额时，再加 `[2]` 打开年报页。对不上就不猜页。

## `lookup_metric`

W6 Agent 应调用这个函数，不要自己拼 SQL：

```python
from app.asknum import lookup_metric

hit = lookup_metric(company_code="002594", concept="revenue", year=2024)
# hit.outcome: ok | human_review | missing | accepted_conflict | not_accepted
```

`try_answer` = `parse_slots` → 循环公司 × 指标 → `lookup_metric` → 模板回复。

## Trace

命中 / 反问 / 拦截都会写入 `asknum_query_log`（叙述题抽出了指标但故意跳过也会记 `route=skip`；「你好」不记）。

评测 runner 传 `persist_trace=False`，避免黄金集污染生产日志。

查询：前端 **问数监控** `/ops/asknum`，或 `GET /ops/asknum-traces`（BFF：`GET /api/ops/asknum-traces`）。

新库由 compose 挂载 `docs/sql/w4_asknum_query_log.sql`。已有库需执行一次：

```bash
docker compose exec -T db psql -U regops -d regops_db -f /docker-entrypoint-initdb.d/05_asknum_log.sql
```

## 评测

黄金集 `eval/golden/w4_asknum_20.json`，20 题覆盖命中、G1 拦截、反问、叙述跳过、ROE/毛利率拦截、库外公司、母公司缺失。

```bash
python-ai/.venv/bin/python eval/run_asknum.py --fail-on-regression
```

指标：`accuracy`（路由 + 槽位 + 取值）、`route_accuracy`、`leak_rate`（拦截路径不得出现金额）。也可在评估报告页跑内置任务 `w4_asknum`。

## 覆盖面（比能力窄时怎么扩）

能力已经能拦 G1、反问、不估数；窄的是仓库：5 家 × 2024 × 合并为主，美的/格力/三一营收在 `human_review`。

正确扩法：再 ingest 公司/年份/母公司、质量页人工通过 G1、以后上 XBRL。不要把 `human_review` 静默放行，也不要手算 ROE 来「显得能答」。

## 不做什么

- 不让 LLM 写 SQL，不做 EXPLAIN 校正循环。
- 不手算 ROE / 毛利率 / 研发强度。
- 不用 `human_review` 的数。
- 不上 LangGraph（那是 W6，工具仍是本模块的 `lookup_metric` / `try_answer`）。
