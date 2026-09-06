<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  getBffHealth,
  getSystemOverview,
  type BffHealth,
  type SystemOverview,
} from '../../api/system'

const overview = ref<SystemOverview | null>(null)
const bffHealth = ref<BffHealth | null>(null)
const loading = ref(true)
const error = ref('')
const autoRefresh = ref(true)

let refreshTimer: ReturnType<typeof setInterval> | null = null

const quickLinks = [
  { label: 'RAG 检索监控', path: '/ops/rag' },
  { label: '问数监控', path: '/ops/asknum' },
  { label: '评估报告', path: '/ops/eval' },
  { label: '解析监控', path: '/ops/ingest' },
  { label: '日志监控', path: '/ops/logs' },
]

function statusClass(status: string) {
  if (status === 'ok') return 'tag ok'
  if (status === 'missing' || status === 'down') return 'tag fail'
  return 'tag warn'
}

function statusLabel(status: string) {
  if (status === 'ok') return '正常'
  if (status === 'down') return '不可用'
  if (status === 'missing') return '未安装'
  return status
}

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

const serviceCards = computed(() => {
  const o = overview.value
  const bff = bffHealth.value
  return [
    {
      name: 'Java BFF',
      status: bff?.status === 'ok' ? 'ok' : 'down',
      detail: bff?.service ?? 'java-service',
      latency: null as number | null,
    },
    {
      name: 'Python AI',
      status: bff?.pythonAi?.status === 'ok' ? 'ok' : o?.services.python_ai.status ?? 'unknown',
      detail: String(bff?.pythonAi?.service ?? o?.services.python_ai.service ?? 'python-ai'),
      latency: null,
    },
    {
      name: 'PostgreSQL',
      status: o?.services.postgresql.status ?? 'unknown',
      detail:
        o?.services.postgresql.latency_ms != null
          ? `${o.services.postgresql.latency_ms} ms`
          : o?.services.postgresql.error ?? '—',
      latency: o?.services.postgresql.latency_ms ?? null,
    },
    {
      name: 'pgvector',
      status: o?.services.pgvector.status ?? 'unknown',
      detail: o?.services.pgvector.installed ? '已安装' : '未检测到扩展',
      latency: null,
    },
  ]
})

const ragOutcomeRows = computed(() => {
  const by = overview.value?.rag_traces.by_outcome ?? {}
  return Object.entries(by).map(([outcome, count]) => ({ outcome, count }))
})

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [ov, bff] = await Promise.all([getSystemOverview(), getBffHealth()])
    overview.value = ov
    bffHealth.value = bff
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function setupAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  if (autoRefresh.value) {
    refreshTimer = setInterval(refresh, 30000)
  }
}

onMounted(async () => {
  await refresh()
  setupAutoRefresh()
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>系统健康</h1>
        <p>服务探活、语料库、入库任务与 RAG 运行概况；每 30 秒可自动刷新。</p>
        <p v-if="overview" class="checked-at">上次检查：{{ formatTime(overview.checked_at) }}</p>
      </div>
      <div class="head-actions">
        <label class="auto-refresh">
          <input v-model="autoRefresh" type="checkbox" @change="setupAutoRefresh" />
          自动刷新
        </label>
        <button type="button" class="ghost-btn" :disabled="loading" @click="refresh">刷新</button>
      </div>
    </header>

    <nav class="quick-links">
      <router-link v-for="link in quickLinks" :key="link.path" :to="link.path" class="quick-link">
        {{ link.label }}
      </router-link>
    </nav>

    <p v-if="loading && !overview" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="overview">
      <div class="stats">
        <article v-for="svc in serviceCards" :key="svc.name" class="stat-card">
          <div class="stat-head">
            <p class="stat-label">{{ svc.name }}</p>
            <span :class="statusClass(svc.status)">{{ statusLabel(svc.status) }}</span>
          </div>
          <p class="stat-value stat-detail">{{ svc.detail }}</p>
        </article>
      </div>

      <div class="grid-2">
        <section class="panel">
          <h2>语料库（pdf_document）</h2>
          <p class="panel-summary">
            Ready {{ overview.corpus.ready_count }} 份 ·
            {{ overview.corpus.total_pages }} 页 ·
            {{ overview.corpus.total_chunks.toLocaleString() }} chunks
          </p>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>doc_id</th>
                  <th>公司</th>
                  <th>年份</th>
                  <th>页数</th>
                  <th>chunks</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in overview.corpus.documents" :key="doc.doc_id">
                  <td class="mono">{{ doc.doc_id }}</td>
                  <td>{{ doc.company_code ?? '—' }}</td>
                  <td>{{ doc.report_year ?? '—' }}</td>
                  <td>{{ doc.page_count }}</td>
                  <td>{{ doc.chunk_count.toLocaleString() }}</td>
                  <td><span :class="statusClass(doc.ingest_status === 'ready' ? 'ok' : 'warn')">{{ doc.ingest_status }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <h2>RAG 运行概况</h2>
          <p class="panel-summary">
            累计 trace {{ overview.rag_traces.total }} 条 · 近 24h {{ overview.rag_traces.last_24h }} 条
          </p>
          <p class="hint rag-note">
            此处为<strong>真实问答</strong> trace 统计；100 题黄金集批量评测请见
            <router-link to="/ops/eval">评估报告</router-link>。
          </p>
          <ul v-if="ragOutcomeRows.length" class="outcome-list">
            <li v-for="row in ragOutcomeRows" :key="row.outcome">
              <span>{{ row.outcome }}</span>
              <strong>{{ row.count }}</strong>
            </li>
          </ul>
          <p v-else class="hint">暂无 RAG trace，去首页提问后会自动记录。</p>
          <router-link to="/ops/rag" class="panel-link">查看 RAG 检索监控 →</router-link>

          <h3 class="sub-title">会话</h3>
          <p class="panel-summary">
            会话 {{ overview.sessions.session_count }} · 待解析上传 {{ overview.sessions.pending_documents }}
          </p>

          <h3 class="sub-title">评测任务</h3>
          <p class="panel-summary">已配置 {{ overview.eval.task_count }} 个任务</p>
          <router-link to="/ops/eval" class="panel-link">评估报告 →</router-link>
        </section>
      </div>

      <section class="panel">
        <h2>入库任务（ingest_job 最近 15 条）</h2>
        <div v-if="overview.ingest_jobs.length" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>job_id</th>
                <th>类型</th>
                <th>doc_id</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="job in overview.ingest_jobs" :key="job.job_id">
                <td class="mono">{{ job.job_id.slice(0, 8) }}…</td>
                <td>{{ job.target_type }}</td>
                <td class="mono">{{ job.target_doc_id }}</td>
                <td><span :class="statusClass(job.status === 'DONE' ? 'ok' : job.status === 'FAILED' ? 'fail' : 'warn')">{{ job.status }}</span></td>
                <td>{{ formatTime(job.created_at) }}</td>
                <td class="error-cell">{{ job.error_message ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="hint">暂无 ingest_job 记录。</p>
      </section>

      <section class="panel">
        <h2>当前配置（只读）</h2>
        <div class="config-grid">
          <div><span class="config-key">default_model</span><span>{{ overview.config.default_model }}</span></div>
          <div><span class="config-key">embedding_model</span><span>{{ overview.config.embedding_model }}</span></div>
          <div><span class="config-key">rag_top_k</span><span>{{ overview.config.rag_top_k }}</span></div>
          <div><span class="config-key">rag_rerank_enabled</span><span>{{ overview.config.rag_rerank_enabled ? '是' : '否' }}</span></div>
          <div><span class="config-key">rag_trace_enabled</span><span>{{ overview.config.rag_trace_enabled ? '是' : '否' }}</span></div>
        </div>
      </section>
    </template>
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
}

.checked-at {
  margin-top: 6px !important;
  font-size: 12px !important;
}

.head-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-muted);
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

.quick-link:hover {
  background: #eff6ff;
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

.stat-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.stat-label {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.stat-value {
  margin: 0;
}

.stat-detail {
  font-size: 14px;
  color: var(--text-strong);
  word-break: break-all;
}

.grid-2 {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 16px;
}

.panel h2 {
  margin: 0 0 8px;
  font-size: 16px;
}

.sub-title {
  margin: 16px 0 6px;
  font-size: 14px;
}

.panel-summary {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-muted);
}

.rag-note {
  margin-bottom: 12px !important;
}

.panel-link {
  display: inline-block;
  margin-top: 8px;
  font-size: 13px;
  color: #2563eb;
  text-decoration: none;
}

.outcome-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.outcome-list li {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px dashed var(--border);
  font-size: 13px;
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
}

.mono {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  font-size: 13px;
}

.config-grid div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  background: #f8fafc;
  border-radius: 8px;
}

.config-key {
  color: var(--text-muted);
  font-family: ui-monospace, Menlo, monospace;
}

.error-cell {
  max-width: 180px;
  color: #b91c1c;
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

.tag.fail {
  background: #fef2f2;
  color: #b91c1c;
}

.tag.warn {
  background: #fff7ed;
  color: #c2410c;
}

.hint {
  color: var(--text-muted);
  font-size: 14px;
}

.error {
  color: #b91c1c;
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .grid-2 {
    grid-template-columns: 1fr;
  }

  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
