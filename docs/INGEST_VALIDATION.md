# 入库三道质量门 · 完整设计稿

> **W2-2 核心文档** · RegOps Copilot ingest 验收标准  
> 配合：[NOISE_PATTERNS.md](./NOISE_PATTERNS.md)（w2-1 上游清洗）· [ACCOUNTING_RULES.md](./ACCOUNTING_RULES.md)（勾稽规则索引）· [W2 清单](./W2_引导式手写清单.html#day23)

---

## 0. 设计目标

PDF 解析入库前，必须通过 **三道可程序化的质量门**：

| 门 | 名称 | 查什么 | 失败语义 |
|----|------|--------|----------|
| **G1** | 金额一致性 | 多路解析对 **同一金融事实** 是否给出相同金额与上下文 | `amount_mismatch` |
| **G2** | 财务勾稽关系 | 已确认的会计等式在归一化金额下是否成立 | `reconciliation_failed` |
| **G3** | 证据坐标完整性 | 关键金额是否可追溯到 **唯一页码 + 有效 BBox** | `missing_or_invalid_bbox` |

**核心修正（相对粗略方案）：**

- ❌ 比较「整页数字集合相似度 ≥95%」——只能做粗预警，**生产不可用**
- ✅ 比较 **同一个金融事实**（concept + period + scope + currency + statement 对齐后再比 value）

原则：**冲突时不自动「挑看起来更合理的数」**；关键项不一致 → `human_review`。

---

## 1. 金融事实（Financial Fact）数据模型

不能只存 `10000`。每个金额至少落为一条 **fact**（与 [XBRL 上下文思想](https://www.xbrl.org/guidance/xbrl-glossary/) 一致：concept、period、entity/scope、unit 共同定义一个数）。

### 1.1 字段定义

```json
{
  "concept": "total_assets",
  "raw_name": "资产总计",
  "raw_value": "1,234.56",
  "value": "1234560000",
  "period": "2025-12-31",
  "scope": "consolidated",
  "currency": "CNY",
  "unit": "万元",
  "statement": "balance_sheet",
  "page_no": 86,
  "bbox": [120, 340, 220, 365],
  "parser": "tableformer",
  "source_file": "600000_2024年报.pdf",
  "content_hash": "sha256:..."
}
```

| 字段 | 说明 |
|------|------|
| `concept` | 统一科目编码（英文 snake_case） |
| `raw_name` / `raw_value` | 报表原文，审计用 |
| `value` | 归一化到 **元** 的整数字符串（或 Decimal 序列化） |
| `period` | 报告期末日 `YYYY-MM-DD` |
| `scope` | `consolidated` / `parent` |
| `statement` | `balance_sheet` / `income` / `cash_flow` |
| `page_no`, `bbox` | G3 证据链 |
| `parser` | `standard` / `tableformer` / `vlm` |

### 1.2 事实唯一键（fact_key）

```text
concept + period + scope + currency + statement
```

同一 `fact_key` 下只允许 **一个** canonical `value` 进入 `fin_metric`；多 parser 产出应合并为一条，冲突则不进库。

### 1.3 与 RegOps 表结构

`fin_metric` 建议字段（W2-2 设计，W2-4 落表）：

```text
company_code, fact_key (hash), concept, period, scope, currency, statement,
value_yuan (NUMERIC), unit_raw, raw_name, raw_value,
page_no, bbox_json, parser, status, review_reason
```

`status`：`auto_accepted` | `human_review` | `rejected`

---

## 2. G1 · 金额一致性

### 2.1 关键科目与别名

```python
CRITICAL_CONCEPTS = {
    "revenue",
    "net_profit",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "operating_cash_flow",
    "cash_end",
    "eps",
}

ALIASES: dict[str, str] = {
    "营业收入": "revenue",
    "营业总收入": "revenue",
    "资产总计": "total_assets",
    "负债合计": "total_liabilities",
    "所有者权益合计": "total_equity",
    "归属于母公司股东的净利润": "net_profit_attributable",
    "净利润": "net_profit",
    # W2-2：按金样本年报继续扩充
}
```

W2-2 验收：≥8 个 `CRITICAL_CONCEPTS` 有中文别名映射，且在 5 份金样本中至少各命中 1 次。

### 2.2 金额归一化（必须 Decimal）

```python
from decimal import Decimal

UNIT_SCALE = {
    "元": Decimal("1"),
    "千元": Decimal("1000"),
    "万元": Decimal("10000"),
    "百万元": Decimal("1000000"),
    "亿元": Decimal("100000000"),
}

def normalize_amount(raw_value: str, unit: str) -> Decimal | None:
    text = raw_value.strip().replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if text in {"", "-", "—", "--", "不适用", "N/A"}:
        return None  # 缺失 ≠ 0
    value = Decimal(text) * UNIT_SCALE[unit]
    return -value if negative else value
```

### 2.3 同事实对齐与比对

```python
def fact_key(fact: dict) -> tuple:
    return (
        fact["concept"],
        fact["period"],
        fact["scope"],
        fact["currency"],
        fact["statement"],
    )

def amount_mismatch(a: dict, b: dict) -> tuple[bool, str]:
    if fact_key(a) != fact_key(b):
        return True, "金额上下文无法对齐"
    if a["value"] != b["value"]:
        return True, f"金额不一致：{a['value']} != {b['value']}"
    return False, ""
```

### 2.4 G1 重点检测清单

- [ ] 两路 parser 同一 `fact_key` 的 `value` 不同
- [ ] 数字相同但 `unit` 不同导致归一化后不同
- [ ] 本期/上期 `period` 错配
- [ ] `consolidated` / `parent` 混淆
- [ ] 括号负数识别成正数
- [ ] `—` 被当成 `0`
- [ ] 同一 `fact_key` 出现多个不同 `value`（重复事实冲突）

### 2.5 G1 验收（W2-2）

| 项 | 标准 |
|----|------|
| 单元测试 | `normalize_amount` 覆盖万元/亿元/括号负/横线缺失 |
| 集成 | 5 家公司年报：关键科目 **零** `critical_amount_mismatch` 自动入库（或全进 review 且原因可追溯） |
| 故意错例 | 测试 fixture 中单位错一行 → 必须拦下 |

---

## 3. G2 · 财务勾稽关系

**不让 LLM 临时编公式。** 规则写在 [ACCOUNTING_RULES.md](./ACCOUNTING_RULES.md)，由程序执行。

### 3.1 已确认等式（示例）

**资产负债表：**

```text
total_assets = total_liabilities + total_equity
```

**现金流量表：**

```text
cash_end = cash_begin + net_cash_change
```

**利润表：**

```text
net_profit = profit_before_tax - income_tax
```

**明确不做：** 看到「毛利率、ROE、EPS」等名称 **相似就手算**——必须 **直读报表字段** 或 XBRL tag（见 [Q26 面试笔记](./面试_工程化笔记.md)）。

### 3.2 通用勾稽函数

```python
from decimal import Decimal

def check_equation(
    name: str,
    left: Decimal | None,
    right_values: list[Decimal | None],
    display_unit: Decimal,
) -> tuple[bool, str]:
    if left is None or any(v is None for v in right_values):
        return False, f"{name}：必要字段缺失"
    difference = abs(left - sum(right_values))
    # 报表按 display_unit（如万元）四舍五入，允许多项累积误差
    tolerance = Decimal(len(right_values) + 1) * display_unit / Decimal("2")
    if difference > tolerance:
        return False, (
            f"{name}勾稽失败：差额={difference}，允许误差={tolerance}"
        )
    return True, ""
```

示例（报表单位为万元）：

```python
passed, err = check_equation(
    name="资产负债表",
    left=total_assets,
    right_values=[total_liabilities, total_equity],
    display_unit=Decimal("10000"),
)
```

### 3.3 G2 验收（W2-2）

| 项 | 标准 |
|----|------|
| 文档 | `ACCOUNTING_RULES.md` 每条含：规则名 · 公式 · 会计依据 · 失败文案 |
| 代码 | `app/ingest/reconciliation.py`（或 `validation.py`）实现 ≥3 条等式 |
| 金样本 | 5 家公司：勾稽 **全部通过** 或标记 `human_review` + 原因 |
| 测试 | 故意改权益一行 → 勾稽必须 fail |

---

## 4. G3 · 证据坐标完整性

RAG 引用与问数审计要求：关键金额能指回 **PDF 上的位置**。

### 4.1 Docling 单元格检查

Docling 的 `TableCell.bbox` 为可选；单元格 **无独立页码**，页码来自 `table.prov`（[Docling 数据结构](https://docling-project.github.io/docling/reference/docling_document/)）。

检查项：

1. `table.prov` 存在
2. 表格对应 **唯一** `page_no`（跨页表单独策略，见下）
3. `cell.bbox` 存在
4. BBox 在页面宽高范围内
5. BBox 面积 > 0

```python
def validate_cell_source(document, table, cell) -> tuple[bool, str | dict]:
    pages = {p.page_no for p in table.prov}
    if len(pages) != 1:
        return False, "单元格无法确定唯一页码"
    if cell.bbox is None:
        return False, "单元格缺少 BBox"
    page_no = next(iter(pages))
    page = document.pages.get(page_no)
    if page is None or page.size is None:
        return False, "缺少页面尺寸"
    box = cell.bbox.to_top_left_origin(page_height=page.size.height)
    valid = (
        0 <= box.l < box.r <= page.size.width
        and 0 <= box.t < box.b <= page.size.height
        and box.area() > 0
    )
    if not valid:
        return False, "BBox 超出页面或面积无效"
    return True, {"page_no": page_no, "bbox": box.model_dump(mode="json")}
```

### 4.2 跨页表格

跨页表 **`len(pages) != 1` 时**：

- 不强行通过 G3；标记 `human_review` 或拆表后再验
- W2-2 金样本中记录跨页表比例；W2-5 再优化策略

### 4.3 增强验证（W2+ 可选）

```text
按 BBox 裁剪原图 → 局部 OCR → 检查是否包含 raw_value
```

裁剪区域无 `raw_value` → 坐标或单元格映射错误。

### 4.4 G3 验收（W2-2）

| 项 | 标准 |
|----|------|
| 范围 | PDF 关键 fact 必须有 `page_no` + 有效 `bbox`；**F10/web** 用 `content_hash` 代替 bbox（见 §7） |
| 金样本 | 5 家公司：**100%** 关键 fact 通过 G3，或进 review 队列 |
| 测试 | fixture 缺 bbox → 必须 fail |

---

## 5. 入库路由（Pipeline）

### 5.1 主路径

```text
Standard 解析（Docling / tableformer）
        ↓
  G0  关键事实是否完整？（CRITICAL_CONCEPTS 齐）
        ├─ 否 → VLM 重试（限 1 次）
        ↓
  G1  金额 / 单位 / 期间 一致？
        ├─ 否 → VLM 重试
        ↓
  G2  勾稽关系通过？
        ├─ 否 → VLM 重试
        ↓
  G3  关键金额有效 BBox？
        ├─ 否 → VLM 重试
        ↓
     自动入库（status=auto_accepted）
```

### 5.2 VLM 重试后

```text
Standard vs VLM 关键金额仍不一致  → human_review
勾稽仍失败                        → human_review
关键金额仍缺坐标                  → human_review
VLM 输出截断 / JSON 解析失败      → human_review
全部通过                          → 接受 VLM 结果（标注 parser=vlm）
```

### 5.3 人工复核记录格式

```json
{
  "status": "human_review",
  "reason": "critical_amount_mismatch",
  "fact_key": "total_assets|2024-12-31|consolidated|CNY|balance_sheet",
  "standard_value": "1234560000000",
  "vlm_value": "1284560000000",
  "page_no": 86,
  "source_file": "600000_2024年报.pdf"
}
```

**禁止：** 两路冲突时静默选较大/较小/较「合理」的一个。

### 5.4 建议代码布局（W2-2 起）

```text
app/ingest/
├── facts.py           # FinancialFact、fact_key、normalize_amount
├── validation.py      # G1/G3 入口
├── reconciliation.py  # G2 入口
└── pipeline.py        # W2-5：路由 + VLM 重试 + ingest_job 状态
```

---

## 6. W2-2 总验收清单

完成 Day 2–3（w2-2）时，**以下全部勾选**方可勾主学习系统 w2-2：

### 文档

- [ ] 本文档 `INGEST_VALIDATION.md` 已读通，三道门能口述
- [ ] `ACCOUNTING_RULES.md` ≥3 条勾稽规则已写会计依据

### G1 金额一致性

- [x] `CRITICAL_CONCEPTS` + `ALIASES` 落地（代码或配置）
- [x] `normalize_amount` 单元测试通过
- [x] 多 parser 同事实比对逻辑可跑（可先 Standard vs 手工 gold）

### G2 财务勾稽

- [x] ≥3 条等式程序校验
- [x] 5 家金样本勾稽报告可导出

### G3 证据坐标

- [x] 关键 fact 的 page_no + bbox 校验（PDF）；F10 用 content_hash
- [x] 5 家金样本关键科目坐标覆盖率 100% 或全进 review

### 金样本

- [x] **5 家公司**年报抽取跑通；无 **静默错误入库**
- [x] 故意错例测试（单位/勾稽/bbox）均能拦下

---

## 7. 与 PDF / XBRL / F10 的关系

| 数据源 | 在三道门中的角色 |
|--------|------------------|
| **PDF 解析** | 产生 fact + bbox；G1–G3 主战场（表格抽取仍可后补） |
| **F10 JSON**（W2-2 原型） | 直读三表写入 `fin_metric`；G1 同 fact_key 冲突、G2 R01–R04、G3=`content_hash` |
| **XBRL**（可选 W4+） | fact 的 concept/period/scope 可对齐 XBRL context；数字冲突时 **结构化源优先** |

W2-2 落地：`python-ai/scripts/download_xbrl.py` 拉 F10，`scripts/ingest_fin_metric.py` 过门入库；看板 `/quality/gates`、`/quality/facts`。

见 [NOISE_PATTERNS.md §2](./NOISE_PATTERNS.md) · 面试笔记 Q26。

---

## 8. 参考

- [XBRL Glossary](https://www.xbrl.org/guidance/xbrl-glossary/)
- [Docling Document model](https://docling-project.github.io/docling/reference/docling_document/)
- [finance-rag-eval 方法提炼](./finance-rag-eval-implementation-guide.html)（若已放入 `docs/`）· 规则与模型分工

---

*版本：w2-validation-v1 · RegOps Copilot*
