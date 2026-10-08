<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  listRagTraces,
  OUTCOME_LABELS,
  type RagOverview,
  type RagTraceItem,
} from '../../api/ops'

const items = ref<RagTraceItem[]>([])
const total = ref(0)
const overview = ref<RagOverview | null>(null)
const loading = ref(true)
const error = ref('')
const outcomeFilter = ref('')
const expandedId = ref<number | null>(null)

const outcomeOptions = [
  { value: '', label: '全部结果' },
  { value: 'ok', label: '成功' },
  { value: 'low_score', label: '分数过低' },
  { value: 'no_intent', label: '无意图' },
  { value: 'no_docs', label: '无文档' },
]

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const traceResponse = await listRagTraces({
      limit: 50,
      outcome: outcomeFilter.value || undefined,
    })
    items.value = traceResponse.items
    total.value = traceResponse.total
    overview.value = traceResponse.summary ?? null
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

function outcomeLabel(outcome: string) {
  return OUTCOME_LABELS[outcome] ?? outcome
}

function outcomeClass(outcome: string) {
  if (outcome === 'ok') return 'tag ok'
  if (outcome === 'low_score') return 'tag warn'
  return 'tag muted'
}

function pagesFromHits(trace: RagTraceItem) {
  const pages = trace.hits.map((hit) => hit.page).filter((p) => p > 0)
  return [...new Set(pages)].sort((a, b) => a - b)
}

const stats = computed(() => {
  const ok = overview.value?.ok_count ?? items.value.filter((item) => item.outcome === 'ok').length
  const low = items.value.filter((item) => item.outcome === 'low_score').length
  const refusalRate = overview.value?.refusal_rate ?? 0
  const refusalCount = overview.value?.refusal_count ?? 0
  const traceTotal = overview.value?.total ?? total.value
  const avgMs =
    overview.value?.avg_rag_ms ??
    (items.value.length === 0
      ? 0
      : Math.round(items.value.reduce((sum, item) => sum + item.total_rag_ms, 0) / items.value.length))
  return { ok, low, refusalRate, refusalCount, traceTotal, avgMs }
})

function formatPercent(rate: number) {
  return `${(rate * 100).toFixed(1)}%`
}

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>RAG 检索监控</h1>
      </div>
      <div class="head-actions">
        <select v-model="outcomeFilter" class="select" @change="refresh">
          <option v-for="opt in outcomeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
        <button type="button" class="send-btn" @click="refresh">刷新</button>
      </div>
    </header>

    <div class="stats">
      <article class="stat-card">
        <p class="stat-label">Trace 总数</p>
        <p class="stat-value">{{ stats.traceTotal }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">成功检索</p>
        <p class="stat-value">{{ stats.ok }}</p>
      </article>
      <article class="stat-card" title="拒答 = 分数过低 + 无文档；分母为排除寒暄（无意图）后的检索次数">
        <p class="stat-label">拒答率</p>
        <p class="stat-value">{{ formatPercent(stats.refusalRate) }}</p>
        <p class="stat-sub">{{ stats.refusalCount }} 次拒答</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">本页 · 分数过低</p>
        <p class="stat-value">{{ stats.low }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">平均 RAG 耗时</p>
        <p class="stat-value">{{ Math.round(stats.avgMs) }} ms</p>
      </article>
    </div>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="!loading && !items.length" class="hint">暂无记录。在首页提问后会自动写入 trace。</p>

    <div v-if="items.length" class="table-wrap">
      <table class="trace-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>问题</th>
            <th>结果</th>
            <th>文档</th>
            <th>命中</th>
            <th>向量分</th>
            <th>耗时</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <template v-for="row in items" :key="row.id">
            <tr>
              <td class="mono">{{ formatTime(row.created_at) }}</td>
              <td class="question" :title="row.question">{{ row.question }}</td>
              <td><span :class="outcomeClass(row.outcome)">{{ outcomeLabel(row.outcome) }}</span></td>
              <td class="mono">{{ row.scoped_doc_ids.join(', ') || '—' }}</td>
              <td>{{ row.final_hit_count }}</td>
              <td class="mono">{{ row.max_vector_score?.toFixed(3) ?? '—' }}</td>
              <td class="mono">{{ Math.round(row.total_rag_ms) }} ms</td>
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
                    <h3>检索参数</h3>
                    <p><strong>关键词：</strong>{{ row.keyword_terms.join(' · ') || '—' }}</p>
                    <p><strong>向量召回：</strong>{{ row.vector_hit_count }} · <strong>关键词召回：</strong>{{ row.keyword_hit_count }}</p>
                    <p><strong>阈值：</strong>{{ row.min_score_threshold ?? '—' }} · <strong>Request ID：</strong>{{ row.request_id ?? '—' }}</p>
                    <p><strong>引用页：</strong>{{ pagesFromHits(row).join(', ') || '—' }}</p>
                  </section>
                  <section>
                    <h3>最终片段 (top-k)</h3>
                    <ul v-if="row.hits.length" class="hit-list">
                      <li v-for="hit in row.hits" :key="`${hit.doc_id}-${hit.chunk_index}`">
                        <span class="mono">#{{ hit.rank }} p{{ hit.page }}</span>
                        <span class="mono">{{ hit.doc_id }} · idx {{ hit.chunk_index }}</span>
                        <span class="mono">score {{ hit.score }}</span>
                        <span v-if="hit.vector_score != null" class="mono">vec {{ hit.vector_score }}</span>
                        <p class="snippet">{{ hit.snippet }}</p>
                      </li>
                    </ul>
                    <p v-else class="hint">无片段</p>
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
