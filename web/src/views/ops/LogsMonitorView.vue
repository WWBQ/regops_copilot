<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  listLogEvents,
  LOG_LEVEL_LABELS,
  LOG_SOURCE_LABELS,
  OUTCOME_LABELS,
  type LogEventItem,
} from '../../api/ops'

const items = ref<LogEventItem[]>([])
const total = ref(0)
const summary = ref<{ by_level: Record<string, number>; by_source: Record<string, number> }>({
  by_level: {},
  by_source: {},
})
const loading = ref(true)
const error = ref('')
const sourceFilter = ref('')
const levelFilter = ref('')
const expandedId = ref<string | null>(null)

const sourceOptions = [
  { value: '', label: '全部来源' },
  { value: 'ingest', label: '入库任务' },
  { value: 'session', label: '会话上传' },
  { value: 'rag', label: 'RAG 检索' },
]

const levelOptions = [
  { value: '', label: '全部级别' },
  { value: 'error', label: '错误' },
  { value: 'warn', label: '警告' },
  { value: 'info', label: '信息' },
]

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

function sourceLabel(source: string) {
  return LOG_SOURCE_LABELS[source] ?? source
}

function levelLabel(level: string) {
  return LOG_LEVEL_LABELS[level] ?? level
}

function levelClass(level: string) {
  if (level === 'error') return 'tag fail'
  if (level === 'warn') return 'tag warn'
  return 'tag info'
}

function toggleExpand(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}

function detailSummary(event: LogEventItem) {
  const d = event.detail
  if (event.source === 'rag' && typeof d.outcome === 'string') {
    return OUTCOME_LABELS[d.outcome] ?? d.outcome
  }
  if (event.source === 'ingest' && typeof d.status === 'string') {
    return String(d.status)
  }
  if (event.source === 'session' && typeof d.status === 'string') {
    return String(d.status)
  }
  return ''
}

const stats = computed(() => ({
  errors: summary.value.by_level.error ?? 0,
  warns: summary.value.by_level.warn ?? 0,
  infos: summary.value.by_level.info ?? 0,
}))

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const response = await listLogEvents({
      limit: 80,
      source: sourceFilter.value || undefined,
      level: levelFilter.value || undefined,
    })
    items.value = response.items
    total.value = response.total
    summary.value = response.summary
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

watch([sourceFilter, levelFilter], refresh)

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>日志监控</h1>
        <p>
          聚合 ingest 失败、会话上传异常与 RAG 非成功 trace（结构化事件，来自数据库）。
          应用控制台日志仍见各服务终端输出。
        </p>
      </div>
      <button type="button" class="ghost-btn" :disabled="loading" @click="refresh">刷新</button>
    </header>

    <nav class="quick-links">
      <router-link to="/ops/ingest" class="quick-link">解析监控</router-link>
      <router-link to="/ops/rag" class="quick-link">RAG 检索监控</router-link>
      <router-link to="/ops/asknum" class="quick-link">问数监控</router-link>
      <router-link to="/ops/health" class="quick-link">系统健康</router-link>
    </nav>

    <div class="stats">
      <article class="stat-card">
        <p class="stat-label">错误</p>
        <p class="stat-value error-num">{{ stats.errors }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">警告</p>
        <p class="stat-value warn-num">{{ stats.warns }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">信息</p>
        <p class="stat-value">{{ stats.infos }}</p>
      </article>
      <article class="stat-card">
        <p class="stat-label">当前列表</p>
        <p class="stat-value">{{ total }}</p>
        <p class="stat-sub">展示 {{ items.length }} 条</p>
      </article>
    </div>

    <div class="filters">
      <select v-model="sourceFilter" class="filter-select">
        <option v-for="opt in sourceOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <select v-model="levelFilter" class="filter-select">
        <option v-for="opt in levelOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
    </div>

    <p v-if="loading && !items.length" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="items.length" class="panel">
      <ul class="event-list">
        <li v-for="event in items" :key="event.id" class="event-row">
          <button type="button" class="event-main" @click="toggleExpand(event.id)">
            <span class="time">{{ formatTime(event.occurred_at) }}</span>
            <span :class="levelClass(event.level)">{{ levelLabel(event.level) }}</span>
            <span class="source">{{ sourceLabel(event.source) }}</span>
            <span class="message">{{ event.message }}</span>
            <span v-if="detailSummary(event)" class="detail-badge">{{ detailSummary(event) }}</span>
          </button>
          <pre v-if="expandedId === event.id" class="event-detail">{{ JSON.stringify(event.detail, null, 2) }}</pre>
        </li>
      </ul>
    </section>
    <p v-else-if="!loading" class="hint">暂无匹配的结构化日志事件。</p>

    <p class="footer-note">
      RAG 成功记录请见
      <router-link to="/ops/rag">RAG 检索监控</router-link>；
      问数 lookup 请见
      <router-link to="/ops/asknum">问数监控</router-link>；
      入库进度请见
      <router-link to="/ops/ingest">解析监控</router-link>。
    </p>
  </section>
</template>

<style scoped>
.page {
  max-width: 960px;
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
  max-width: 680px;
}

.quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.quick-link {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
  color: #2563eb;
  text-decoration: none;
  background: var(--surface);
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
  font-size: 13px;
  color: var(--text-muted);
}

.stat-value {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
}

.error-num {
  color: #b91c1c;
}

.warn-num {
  color: #c2410c;
}

.stat-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--surface);
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0;
  overflow: hidden;
}

.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.event-row {
  border-bottom: 1px solid var(--border);
}

.event-row:last-child {
  border-bottom: none;
}

.event-main {
  width: 100%;
  display: grid;
  grid-template-columns: 140px 56px 80px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.event-main:hover {
  background: #f8fafc;
}

.time {
  font-size: 12px;
  color: var(--text-muted);
}

.source {
  font-size: 12px;
  color: #64748b;
}

.message {
  font-size: 13px;
  color: var(--text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
}

.event-detail {
  margin: 0;
  padding: 12px 16px 16px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 12px;
  overflow: auto;
}

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.tag.fail {
  background: #fef2f2;
  color: #b91c1c;
}

.tag.warn {
  background: #fff7ed;
  color: #c2410c;
}

.tag.info {
  background: #eff6ff;
  color: #1d4ed8;
}

.hint {
  color: var(--text-muted);
  font-size: 14px;
}

.error {
  color: #b91c1c;
}

.footer-note {
  margin-top: 16px;
  font-size: 13px;
  color: var(--text-muted);
}

.footer-note a {
  color: #2563eb;
}

@media (max-width: 768px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .event-main {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .message {
    white-space: normal;
  }
}
</style>
