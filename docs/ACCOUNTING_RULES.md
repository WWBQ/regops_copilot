# ACCOUNTING_RULES · 财务勾稽规则索引

> **G2 财务勾稽关系** 的规则清单。完整设计见 [INGEST_VALIDATION.md](./INGEST_VALIDATION.md)。  
> W2-2 要求：每条规则写清 **公式 · 会计依据 · 实现位置 · 失败告警文案**。

---

## 使用边界

- ✅ 只对 **已确认的报表内恒等式** 做程序校验  
- ❌ 不因名称相似自行计算 **ROE、毛利率、EPS** 等——必须 **直读报表** 或 XBRL tag  
- 金额一律 `Decimal`；容差与报表 **显示单位**（万元等）挂钩，见 INGEST_VALIDATION §3.2  
- R04 缺少数股东损益 / 归母净利润时 **skip**，不反算、不记 fail  

---

## 规则表

| ID | 规则名 | 公式 | 适用 scope | 会计依据 | 代码 | 状态 |
|----|--------|------|------------|----------|------|------|
| R01 | 资产负债表恒等式 | `total_assets = total_liabilities + total_equity` | consolidated, parent | 会计恒等式：资产 = 负债 + 所有者权益 | `reconciliation.py` | 已实现 |
| R02 | 现金期末余额 | `cash_end = cash_begin + net_cash_change` | consolidated | 现金流量表直接法/间接法期末调节 | `reconciliation.py` | 已实现 |
| R03 | 净利润 | `net_profit = profit_before_tax - income_tax` | consolidated | 利润表行次勾稽 | `reconciliation.py` | 已实现 |
| R04 | 归母 vs 净利润 | `net_profit = net_profit_attributable + minority_interest` | consolidated | 合并利润表：归母 + 少数股东损益 = 净利润 | `reconciliation.py` | 已实现 |

---

## R01 · 资产负债表恒等式

**公式：**

```text
资产总计 = 负债合计 + 所有者权益合计
```

**concept 映射：**

- `total_assets` ← 资产总计  
- `total_liabilities` ← 负债合计  
- `total_equity` ← 所有者权益合计  

**失败文案示例：**

```text
资产负债表勾稽失败：资产总计 {left} ≠ 负债合计 {liab} + 权益合计 {equity}，差额 {diff}（允许误差 {tol}）
```

**会计依据：** 复式记账恒等式；合并报表与母公司报表须分别校验，不得混用 scope。

---

## R02 · 现金流量表期末现金

**公式：**

```text
期末现金及现金等价物余额 = 期初余额 + 现金及现金等价物净增加额
```

**concept：** `cash_end`, `cash_begin`, `net_cash_change`

**注意：** 部分年报「现金及现金等价物」与「货币资金」口径不同——以报表 **行标题原文** 为准，写入 `raw_name` 审计。

---

## R03 · 利润表净利润

**公式：**

```text
净利润 = 利润总额 - 所得税费用
```

**concept：** `net_profit`, `profit_before_tax`, `income_tax`

---

## R04 · 归母 vs 净利润

**公式：**

```text
净利润 = 归属于母公司股东的净利润 + 少数股东损益
```

**concept：** `net_profit`, `net_profit_attributable`, `minority_interest`（F10 字段 `PARENT_NETPROFIT` / `MINORITY_INTEREST`）

**缺数策略：** 任一字段缺失 → `skipped=true`，**不**把差额反算成缺失科目写入库；也不记 G2 fail。

**失败文案示例：**

```text
归母勾稽失败：净利润 {left} ≠ 归母净利润 {attr} + 少数股东损益 {min}，差额 {diff}
```

---

## 验收

- [x] 上表 R01–R04 状态改为「已实现」
- [x] `tests/test_financial.py` 含勾稽 pass + fail + R04 skip 用例
- [x] 5 家金样本勾稽报告可导出（`GET /ops/quality/gates` + CLI `ingest_fin_metric.py`）

详见 [INGEST_VALIDATION.md §6 W2-2 总验收](./INGEST_VALIDATION.md#6-w2-2-总验收清单)。
