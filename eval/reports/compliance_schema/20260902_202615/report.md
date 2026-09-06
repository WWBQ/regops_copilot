# 合规结论 Schema 校验报告

- 校验对象：`app.schemas.compliance.ComplianceConclusion`
- 黄金集：compliance_schema_20.json（compliance-schema-v1）
- 生成时间：2026-09-02T12:26:15.515469+00:00
- 样本数：20（合法 10 / 非法 10）

## 总体指标

| 指标 | 数值 | 含义 |
|------|------|------|
| accuracy | 100.00% | 放行/拒绝方向判对的比例 |
| false_accept_rate | 0.00% | 非法样例被误放行（越低越好，合规红线）|
| false_reject_rate | 0.00% | 合法样例被误拒（影响可用性）|
| rule_hit_rate | 100.00% | 非法样例被拒且报错理由命中预期规则 |
| strict_pass_rate | 100.00% | 方向 + 理由 + 字段清洗全部正确 |

字段清洗断言：2/2 通过

## 按规则

| 规则 | 样本 | 通过 | 失败 |
|------|------|------|------|
| baseline_low_risk | 1 | 1 | 0 |
| baseline_multi_clause | 1 | 1 | 0 |
| high_risk_confidence_boundary | 1 | 1 | 0 |
| confidence_lower_boundary | 1 | 1 | 0 |
| confidence_upper_boundary | 1 | 1 | 0 |
| optional_field_default | 1 | 1 | 0 |
| clause_refs_strip | 1 | 1 | 0 |
| conclusion_max_len_boundary | 1 | 1 | 0 |
| high_risk_low_confidence | 1 | 1 | 0 |
| baseline_multi_evidence | 1 | 1 | 0 |
| clause_refs_min_len | 1 | 1 | 0 |
| clause_refs_blank_only | 1 | 1 | 0 |
| risk_level_enum | 1 | 1 | 0 |
| confidence_gt_one | 1 | 1 | 0 |
| confidence_lt_zero | 1 | 1 | 0 |
| high_risk_confidence_cap | 1 | 1 | 0 |
| conclusion_empty | 1 | 1 | 0 |
| conclusion_too_long | 1 | 1 | 0 |
| conclusion_missing | 1 | 1 | 0 |
| confidence_not_numeric | 1 | 1 | 0 |

## 失败样例

无。
