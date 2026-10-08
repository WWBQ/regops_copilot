<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  METRIC_STATUS_LABELS,
  STATEMENT_LABELS,
  listFinMetrics,
  type FinMetricItem,
} from '../../api/quality'

const route = useRoute()
const router = useRouter()

const items = ref<FinMetricItem[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const companyCode = ref(String(route.query.company_code ?? ''))
const status = ref(String(route.query.status ?? ''))
const statement = ref(String(route.query.statement ?? ''))
const concept = ref(String(route.query.concept ?? ''))

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const response = await listFinMetrics({
      limit: 200,
      company_code: companyCode.value || undefined,
      status: status.value || undefined,
      statement: statement.value || undefined,
      concept: concept.value || undefined,
    })
    items.value = response.items
    total.value = response.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function syncQuery() {
  const query: Record<string, string> = {}
  if (companyCode.value) query.company_code = companyCode.value
  if (status.value) query.status = status.value
  if (statement.value) query.statement = statement.value
  if (concept.value) query.concept = concept.value
  router.replace({ path: '/quality/facts', query })
}

watch([companyCode, status, statement, concept], () => {
  syncQuery()
  void refresh()
})

onMounted(refresh)

function statusClass(value: string) {
  if (value === 'auto_accepted' || value === 'manually_accepted') return 'tag ok'
  if (value === 'human_review') return 'tag warn'
  return 'tag fail'
}
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>财务事实库</h1>
      </div>
        <button type="button" class="ghost-btn" @click="refresh">刷新</button>
    </header>

    <div class="filters">
      <select v-model="companyCode" class="filter-select">
        <option value="">全部公司</option>
        <option value="002594">比亚迪 002594</option>
        <option value="601633">长城汽车 601633</option>
        <option value="000333">美的集团 000333</option>
        <option value="000651">格力电器 000651</option>
        <option value="600031">三一重工 600031</option>
        <option value="300750">宁德时代 300750</option>
        <option value="600519">贵州茅台 600519</option>
      </select>
      <select v-model="statement" class="filter-select">
        <option value="">全部报表</option>
        <option value="balance_sheet">资产负债表</option>
        <option value="income">利润表</option>
        <option value="cash_flow">现金流量表</option>
      </select>
      <select v-model="status" class="filter-select">
        <option value="">全部状态</option>
        <option value="auto_accepted">自动通过</option>
        <option value="human_review">待审核</option>
        <option value="manually_accepted">人工确认</option>
        <option value="rejected">已拒绝</option>
      </select>
      <select v-model="concept" class="filter-select">
        <option value="">全部指标</option>
        <option value="revenue">营业收入</option>
        <option value="net_profit">净利润</option>
        <option value="total_assets">资产总计</option>
        <option value="total_liabilities">负债合计</option>
        <option value="total_equity">所有者权益合计</option>
        <option value="operating_cash_flow">经营现金流</option>
        <option value="eps">每股收益</option>
      </select>
    </div>

    <p v-if="loading && !items.length" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p class="hint">共 {{ total }} 条</p>

    <section class="panel">
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>公司</th>
              <th>科目</th>
              <th>报表</th>
              <th>期间</th>
              <th>金额</th>
              <th>原文</th>
              <th>状态</th>
              <th>原因</th>
              <th>审核</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in items" :key="row.id">
              <td>{{ row.company_name ?? row.company_code }}</td>
              <td>{{ row.raw_name ?? row.concept }} <span class="mono">{{ row.concept }}</span></td>
              <td>{{ STATEMENT_LABELS[row.statement] ?? row.statement }}</td>
              <td>{{ row.period }}</td>
              <td>{{ row.value_display ?? row.value_yuan ?? '—' }}</td>
              <td class="mono">{{ row.raw_value ?? '—' }}</td>
              <td>
                <span :class="statusClass(row.status)">
                  {{ METRIC_STATUS_LABELS[row.status] ?? row.status }}
                </span>
              </td>
              <td>{{ row.review_reason ?? '—' }}</td>
              <td>
                <router-link
                  v-if="row.status === 'human_review' || row.status === 'manually_accepted' || row.status === 'rejected'"
                  :to="{ path: row.status === 'human_review' ? '/quality/review/pending' : '/quality/review/completed', query: { fact_id: String(row.id) } }"
                >{{ row.status === 'human_review' ? '去审核' : '查看记录' }}</router-link>
                <span v-else>—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!loading && !items.length" class="hint">暂无财务事实。可在左侧切换到「质量门」入库 F10。</p>
    </section>
  </section>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.head h1 {
  margin: 0 0 8px;
  font-size: 24px;
}
.head p {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
  max-width: 720px;
}
.ghost-btn {
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface);
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.filter-select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--surface);
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
.table-wrap {
  overflow: auto;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
.mono {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
  color: var(--text-muted);
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.tag.ok {
  background: #ecfdf5;
  color: #047857;
}
.tag.warn {
  background: #fff7ed;
  color: #c2410c;
}
.tag.fail {
  background: #fef2f2;
  color: #b91c1c;
}
.hint {
  color: var(--text-muted);
  font-size: 14px;
}
.error {
  color: #b91c1c;
}
</style>
