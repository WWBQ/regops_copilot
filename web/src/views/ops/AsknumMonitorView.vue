<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  ASKNUM_LOOKUP_LABELS,
  ASKNUM_ROUTE_LABELS,
  listAsknumTraces,
  type AsknumOverview,
  type AsknumTraceItem,
} from '../../api/ops'

const CONCEPT_LABELS: Record<string, string> = {
  revenue: '营业收入',
  net_profit: '净利润',
  net_profit_attributable: '归母净利润',
  total_assets: '总资产',
  total_liabilities: '总负债',
  total_equity: '净资产',
  operating_cash_flow: '经营现金流',
  eps: '每股收益',
}

const items = ref<AsknumTraceItem[]>([])
const total = ref(0)
const overview = ref<AsknumOverview | null>(null)
const loading = ref(true)
const error = ref('')
const routeFilter = ref('')
const expandedId = ref<number | null>(null)

const routeOptions = [
  { value: '', label: '全部路由' },
  { value: 'metric', label: '命中' },
  { value: 'metric_blocked', label: '拦截' },
  { value: 'metric_clarify', label: '反问' },
  { value: 'skip', label: '跳过' },
]

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const response = await listAsknumTraces({
      limit: 50,
      route: routeFilter.value || undefined,
    })
    items.value = response.items
    total.value = response.total
    overview.value = response.summary ?? null
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

function routeLabel(route: string) {
  return ASKNUM_ROUTE_LABELS[route] ?? route
}

function routeClass(route: string) {
  if (route === 'metric') return 'tag ok'
  if (route === 'metric_blocked') return 'tag warn'
  if (route === 'metric_clarify') return 'tag info'
  return 'tag muted'
}

function lookupLabel(outcome: string) {
  return ASKNUM_LOOKUP_LABELS[outcome] ?? outcome
}

function conceptLabel(concept: string) {
  return CONCEPT_LABELS[concept] ?? concept
}

function formatConcepts(concepts: string[]) {
  return concepts.map(conceptLabel).join('、') || '—'
}

const stats = computed(() => {
  const summary = overview.value
  return {
    total: summary?.total ?? total.value,
    metric: summary?.metric_count ?? 0,
    blocked: summary?.blocked_count ?? 0,
    clarify: summary?.clarify_count ?? 0,
    skip: summary?.skip_count ?? 0,
    avgMs: summary?.avg_ms ?? 0,
  }
})

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>问数监控</h1>
        <p>
          记录首页真实提问里走 <code>fin_metric</code> 的 trace（命中 / 拦截 / 反问 / 叙述跳过）。
          「你好」不会落库。与评估报告 20 题黄金集不是同一回事。
        </p>
        <p class="head-link">
          <router-link to="/ops/eval">→ 跑 W4 问数 20 题评测</router-link>
          ·
          <router-link to="/ops/rag">RAG 检索监控</router-link>
        </p>
      </div>
      <div class="head-actions">
        <select v-model="routeFilter" class="select" @change="refresh">
          <option v-for="opt in routeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button type="button" class="send-btn" @click="refresh">刷新</button>
      </div>
    </header>

    <div class="stats">
      <article class="stat-card">
        <p class="stat-label">Trace 总数</p>
        <p class="stat-value">{{ stats.total }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">命中</p>
        <p class="stat-value">{{ stats.metric }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">拦截</p>
        <p class="stat-value">{{ stats.blocked }}</p>
        <p class="stat-sub">待复核 / 缺失 / 冲突</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">反问 · 跳过</p>
        <p class="stat-value">{{ stats.clarify }} · {{ stats.skip }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">平均耗时</p>
        <p class="stat-value">{{ Math.round(stats.avgMs) }} ms</p>
      </article>
    </div>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="!loading && !items.length" class="hint">
      暂无记录。在首页问「比亚迪 2024 营收多少」会写入；评测不会污染此表。
    </p>

    <div v-if="items.length" class="table-wrap">
      <table class="trace-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>问题</th>
            <th>路由</th>
            <th>公司</th>
            <th>指标</th>
            <th>年份</th>
            <th>耗时</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template v-for="row in items" :key="row.id">
            <tr>
              <td class="mono">{{ formatTime(row.created_at) }}</td>
              <td class="question" :title="row.question">{{ row.question }}</td>
              <td><span :class="routeClass(row.route)">{{ routeLabel(row.route) }}</span></td>
              <td class="mono">{{ row.company_codes.join(', ') || '—' }}</td>
              <td>{{ formatConcepts(row.concepts) }}</td>
              <td class="mono">
                {{ row.year ?? '—' }}
                <span v-if="row.year_defaulted" class="muted">默认</span>
              </td>
              <td class="mono">{{ Math.round(row.total_ms) }} ms</td>
              <td>
                <button type="button" class="ghost-btn" @click="toggleExpand(row.id)">
                  {{ expandedId === row.id ? '收起' : '详情' }}
                </button>
              </td>
            </tr>
            <tr v-if="expandedId === row.id" class="detail-row">
              <td colspan="8">
                <div class="detail-grid">
                  <section>
                    <h3>槽位</h3>
                    <p><strong>口径：</strong>{{ row.scope === 'parent' ? '母公司' : '合并报表' }}</p>
                    <p><strong>叙述题：</strong>{{ row.narrative ? '是（跳过问数）' : '否' }}</p>
                    <p><strong>Request ID：</strong>{{ row.request_id ?? '—' }}</p>
                    <p><strong>Session：</strong>{{ row.session_id ?? '—' }}</p>
                  </section>
                  <section>
                    <h3>lookup</h3>
                    <ul v-if="row.lookups.length" class="hit-list">
                      <li v-for="(hit, index) in row.lookups" :key="`${hit.company_code}-${hit.concept}-${index}`">
                        <span class="mono">{{ hit.company_code }} / {{ conceptLabel(hit.concept) }}</span>
                        <span :class="hit.outcome === 'ok' ? 'tag ok' : 'tag warn'">
                          {{ lookupLabel(hit.outcome) }}
                        </span>
                        <span v-if="hit.value_yuan" class="mono">{{ hit.value_yuan }}</span>
                        <p v-if="hit.doc_id" class="snippet">doc_id={{ hit.doc_id }}</p>
                        <p v-if="hit.review_reason" class="snippet">{{ hit.review_reason }}</p>
                      </li>
                    </ul>
                    <p v-else class="hint">无 lookup（反问或跳过）</p>
                  </section>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
}

.head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.head h1 {
  margin: 0 0 8px;
  font-size: 24px;
  color: var(--text-strong);
}

.head p {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.5;
}

.head-link {
  margin-top: 8px !important;
}

.head-link a {
  color: #2563eb;
  text-decoration: none;
}

.head-link a:hover {
  text-decoration: underline;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.select {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--surface);
  color: var(--text);
}

.stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.stat-label {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.stat-value {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-strong);
}

.stat-sub {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}

.table-wrap {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.trace-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.trace-table th,
.trace-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.trace-table th {
  background: #f8fafc;
  color: var(--text-muted);
  font-weight: 600;
}

.question {
  max-width: 280px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.muted {
  color: var(--text-muted);
  font-size: 11px;
  margin-left: 4px;
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

.tag.info {
  background: #eff6ff;
  color: #1d4ed8;
}

.tag.muted {
  background: #f1f5f9;
  color: #64748b;
}

.detail-row td {
  background: #fafafa;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 20px;
}

.detail-grid h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.detail-grid p {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.5;
}

.hit-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.hit-list li {
  padding: 8px 0;
  border-bottom: 1px dashed var(--border);
}

.hit-list li:last-child {
  border-bottom: none;
}

.snippet {
  margin: 4px 0 0;
  color: var(--text-muted);
  line-height: 1.45;
}

.hint {
  color: var(--text-muted);
  font-size: 14px;
}

.error {
  color: #b91c1c;
  font-size: 14px;
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .head {
    flex-direction: column;
  }
}
</style>
