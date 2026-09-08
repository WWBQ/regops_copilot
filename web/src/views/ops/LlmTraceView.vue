<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { listObsTraces, type LlmObsOverview, type LlmTraceItem } from '../../api/ops'

const items = ref<LlmTraceItem[]>([])
const total = ref(0)
const overview = ref<LlmObsOverview | null>(null)
const loading = ref(true)
const error = ref('')
const expandedId = ref<string | null>(null)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const response = await listObsTraces({ limit: 50 })
    items.value = response.items
    total.value = response.total
    overview.value = response.summary ?? null
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function toggleExpand(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

function formatUsd(value: number | null | undefined) {
  if (value == null) return '—'
  return `$${value.toFixed(6)}`
}

const stats = computed(() => {
  const summary = overview.value
  return {
    count: summary?.count ?? total.value,
    p95: summary?.p95_latency_ms,
    ttft: summary?.ttft_p95_ms,
    tokensPerS: summary?.avg_tokens_per_s,
    cost: summary?.cost_usd_sum ?? 0,
    langfuse: summary?.langfuse_enabled ? '已启用' : '本地缓冲',
  }
})

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>LLM Trace</h1>
        <p>
          一次问答记下 Prompt 钉扎版本、Token、估算成本和 W3C <code>traceparent</code>。
          未配 Langfuse Key 时只留在 Python 进程内的环形缓冲（约 200 条），敏感字段已脱敏。
        </p>
        <p class="head-link">
          <router-link to="/ops/health">系统健康</router-link>
          ·
          <router-link to="/ops/eval">评估报告</router-link>
        </p>
      </div>
      <div class="head-actions">
        <button type="button" class="send-btn" @click="refresh">刷新</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="muted">加载中…</p>

    <div class="stats">
      <article class="stat-card">
        <p class="stat-label">Generation</p>
        <p class="stat-value">{{ stats.count }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">P95 延迟</p>
        <p class="stat-value">{{ stats.p95 == null ? '—' : `${Math.round(stats.p95)} ms` }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">TTFT P95</p>
        <p class="stat-value">{{ stats.ttft == null ? '—' : `${Math.round(stats.ttft)} ms` }}</p>
        <p class="stat-sub">仅流式有值</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">tokens/s</p>
        <p class="stat-value">{{ stats.tokensPerS == null ? '—' : stats.tokensPerS }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">估算成本</p>
        <p class="stat-value">{{ formatUsd(stats.cost) }}</p>
        <p class="stat-sub">{{ stats.langfuse }}</p>
      </article>
    </div>
    <p v-if="overview?.note" class="muted">{{ overview.note }}</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>路由</th>
            <th>Prompt</th>
            <th>Token</th>
            <th>延迟</th>
            <th>成本</th>
            <th>Trace</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!items.length && !loading">
            <td colspan="7" class="muted">还没有模型调用。去首页问一句后再刷新。</td>
          </tr>
          <template v-for="row in items" :key="row.id">
            <tr class="row" @click="toggleExpand(row.id)">
              <td>{{ formatTime(row.created_at) }}</td>
              <td>{{ row.route }}</td>
              <td>
                <span v-if="row.prompt_name">{{ row.prompt_name }}@{{ row.prompt_version || '—' }}</span>
                <span v-else class="muted">问数 0 token</span>
              </td>
              <td>{{ row.total_tokens }}</td>
              <td>{{ Math.round(row.latency_ms) }} ms</td>
              <td>{{ formatUsd(row.cost_usd) }}</td>
              <td class="mono">{{ row.trace_id.slice(0, 16) }}</td>
            </tr>
            <tr v-if="expandedId === row.id" class="detail">
              <td colspan="7">
                <p>request_id：<code>{{ row.request_id }}</code></p>
                <p v-if="row.traceparent">traceparent：<code>{{ row.traceparent }}</code></p>
                <p v-if="row.input">输入（已脱敏）：{{ row.input }}</p>
                <p v-if="row.output">输出（已脱敏）：{{ row.output }}</p>
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

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
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
}

.stat-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.table-wrap {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.row {
  cursor: pointer;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.muted {
  color: var(--text-muted);
}

.error {
  color: #b91c1c;
}

.send-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 14px;
  background: var(--surface);
  cursor: pointer;
}
</style>
