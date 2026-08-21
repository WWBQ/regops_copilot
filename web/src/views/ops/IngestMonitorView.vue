<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  getIngestOverview,
  INGEST_STATUS_LABELS,
  listIngestJobs,
  listSessionIngestDocuments,
  type IngestJobItem,
  type IngestOverview,
  type SessionIngestDocument,
} from '../../api/ops'

const overview = ref<IngestOverview | null>(null)
const jobs = ref<IngestJobItem[]>([])
const jobsTotal = ref(0)
const sessionDocs = ref<SessionIngestDocument[]>([])
const sessionTotal = ref(0)
const loading = ref(true)
const error = ref('')
const jobStatusFilter = ref('')
const sessionStatusFilter = ref('')

const jobStatusOptions = [
  { value: '', label: '全部状态' },
  { value: 'PENDING', label: '待处理' },
  { value: 'PARSING', label: '解析中' },
  { value: 'DONE', label: '完成' },
  { value: 'FAILED', label: '失败' },
]

const sessionStatusOptions = [
  { value: '', label: '全部状态' },
  { value: 'PENDING', label: '待处理' },
  { value: 'PROCESSING', label: '处理中' },
  { value: 'READY', label: '就绪' },
  { value: 'FAILED', label: '失败' },
]

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function statusLabel(status: string) {
  return INGEST_STATUS_LABELS[status] ?? status
}

function statusClass(status: string) {
  if (status === 'ready' || status === 'READY' || status === 'DONE') return 'tag ok'
  if (status === 'failed' || status === 'FAILED') return 'tag fail'
  if (status === 'processing' || status === 'PROCESSING' || status.startsWith('PAR')) return 'tag warn'
  return 'tag muted'
}

const corpusStats = computed(() => {
  const c = overview.value?.corpus
  if (!c) return { docs: 0, pages: 0, chunks: 0, parseArtifacts: 0 }
  return {
    docs: c.documents.length,
    pages: c.total_pages,
    chunks: c.total_chunks,
    parseArtifacts: c.with_parse_artifact,
  }
})

async function refreshOverview() {
  overview.value = await getIngestOverview()
}

async function refreshJobs() {
  const response = await listIngestJobs({
    limit: 50,
    status: jobStatusFilter.value || undefined,
  })
  jobs.value = response.items
  jobsTotal.value = response.total
}

async function refreshSessionDocs() {
  const response = await listSessionIngestDocuments({
    limit: 30,
    status: sessionStatusFilter.value || undefined,
  })
  sessionDocs.value = response.items
  sessionTotal.value = response.total
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([refreshOverview(), refreshJobs(), refreshSessionDocs()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

watch(jobStatusFilter, refreshJobs)
watch(sessionStatusFilter, refreshSessionDocs)

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>解析监控</h1>
        <p>
          批量年报入库（pdf_document）与会话 PDF 上传（session_document / ingest_job）进度。
          批量入库走 CLI；合规问答页可上传会话附件。
        </p>
      </div>
      <button type="button" class="ghost-btn" :disabled="loading" @click="refresh">刷新</button>
    </header>

    <nav class="quick-links">
      <router-link to="/ops/health" class="quick-link">系统健康</router-link>
      <router-link to="/ops/rag" class="quick-link">RAG 检索监控</router-link>
      <router-link to="/ops/logs" class="quick-link">日志监控</router-link>
    </nav>

    <p v-if="loading && !overview" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="overview">
      <div class="stats">
        <article class="stat-card">
          <p class="stat-label">语料库文档</p>
          <p class="stat-value">{{ corpusStats.docs }}</p>
          <p class="stat-sub">{{ corpusStats.pages }} 页 · {{ corpusStats.chunks.toLocaleString() }} chunks</p>
        </article>
        <article class="stat-card">
          <p class="stat-label">解析产物</p>
          <p class="stat-value">{{ corpusStats.parseArtifacts }}</p>
          <p class="stat-sub">含 parse.json 回溯</p>
        </article>
        <article class="stat-card">
          <p class="stat-label">入库任务</p>
          <p class="stat-value">{{ overview.jobs.total }}</p>
          <p class="stat-sub">进行中 {{ overview.jobs.pending }} · 24h 失败 {{ overview.jobs.failed_24h }}</p>
        </article>
        <article class="stat-card">
          <p class="stat-label">会话上传</p>
          <p class="stat-value">{{ overview.session_uploads.total }}</p>
          <p class="stat-sub">待完成 {{ overview.session_uploads.pending }}</p>
        </article>
      </div>

      <section class="panel">
        <h2>语料库（pdf_document）</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>doc_id</th>
                <th>公司</th>
                <th>年份</th>
                <th>页数</th>
                <th>chunks</th>
                <th>大小</th>
                <th>content_hash</th>
                <th>parse</th>
                <th>状态</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="doc in overview.corpus.documents" :key="doc.doc_id">
                <td class="mono">{{ doc.doc_id }}</td>
                <td>{{ doc.company_code ?? '—' }}</td>
                <td>{{ doc.report_year ?? '—' }}</td>
                <td>{{ doc.page_count }}</td>
                <td>{{ doc.chunk_count.toLocaleString() }}</td>
                <td>{{ formatBytes(doc.file_size_bytes) }}</td>
                <td class="mono hash">{{ doc.content_hash.slice(0, 12) }}…</td>
                <td>{{ doc.has_parse_artifact ? '✓' : '—' }}</td>
                <td><span :class="statusClass(doc.ingest_status)">{{ statusLabel(doc.ingest_status) }}</span></td>
                <td>{{ formatTime(doc.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head">
            <h2>ingest_job（{{ jobsTotal }}）</h2>
            <select v-model="jobStatusFilter" class="filter-select">
              <option v-for="opt in jobStatusOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>job_id</th>
                  <th>类型</th>
                  <th>doc_id</th>
                  <th>状态</th>
                  <th>重试</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="job in jobs" :key="job.job_id">
                  <td class="mono">{{ job.job_id.slice(0, 8) }}…</td>
                  <td>{{ job.target_type }}</td>
                  <td class="mono">{{ job.target_doc_id }}</td>
                  <td><span :class="statusClass(job.status)">{{ statusLabel(job.status) }}</span></td>
                  <td>{{ job.retry_count }}</td>
                  <td>{{ formatTime(job.updated_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!jobs.length" class="hint">暂无入库任务。</p>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>会话上传（{{ sessionTotal }}）</h2>
            <select v-model="sessionStatusFilter" class="filter-select">
              <option v-for="opt in sessionStatusOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>文件名</th>
                  <th>doc_id</th>
                  <th>状态</th>
                  <th>页/chunks</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in sessionDocs" :key="`${doc.session_id}:${doc.doc_id}`">
                  <td>{{ doc.source_filename }}</td>
                  <td class="mono">{{ doc.doc_id }}</td>
                  <td><span :class="statusClass(doc.status)">{{ statusLabel(doc.status) }}</span></td>
                  <td>{{ doc.page_count ?? '—' }} / {{ doc.chunk_count ?? '—' }}</td>
                  <td>{{ formatTime(doc.updated_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="!sessionDocs.length" class="hint">暂无会话上传记录。</p>
        </section>
      </div>
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
  max-width: 720px;
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

.stat-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 16px;
}

.panel h2 {
  margin: 0;
  font-size: 16px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.filter-select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--surface);
}

.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
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

.hash {
  max-width: 100px;
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

.tag.muted {
  background: #f1f5f9;
  color: #64748b;
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
}
</style>
