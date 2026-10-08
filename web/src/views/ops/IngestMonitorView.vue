<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  getIngestOverview,
  INGEST_STATUS_LABELS,
  listSessionIngestDocuments,
  listIngestBatches,
  type IngestBatchItem,
  type IngestOverview,
  type SessionIngestDocument,
} from '../../api/ops'
import IngestBatchChart from '../../components/ops/IngestBatchChart.vue'

const overview = ref<IngestOverview | null>(null)
const sessionDocs = ref<SessionIngestDocument[]>([])
const sessionTotal = ref(0)
const loading = ref(true)
const error = ref('')
const sessionStatusFilter = ref('')
const batches = ref<IngestBatchItem[]>([])
const batchesTotal = ref(0)
const batchStatusFilter = ref('')
const batchParserFilter = ref('')
const keywordInput = ref('')
const batchKeyword = ref('')
const batchOffset = ref(0)
const batchLimit = 20
let pollTimer: ReturnType<typeof setInterval> | undefined
let polling = false

const batchStatusOptions = [
  { value: '', label: '全部状态' },
  { value: 'QUEUED', label: '排队中' },
  { value: 'RUNNING', label: '执行中' },
  { value: 'DONE', label: '完成' },
  { value: 'PARTIAL', label: '部分失败' },
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
  if (status === 'processing' || status === 'PROCESSING' || status === 'PENDING' || status === 'QUEUED' || status === 'RUNNING' || status === 'PARTIAL') return 'tag warn'
  if (status === 'PARSING' || status === 'CLEANING' || status === 'CHUNKING' || status === 'EMBEDDING' || status === 'EXTRACTING') {
    return 'tag warn'
  }
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

async function refreshSessionDocs() {
  const response = await listSessionIngestDocuments({
    limit: 30,
    status: sessionStatusFilter.value || undefined,
  })
  sessionDocs.value = response.items
  sessionTotal.value = response.total
}

async function refreshBatches() {
  const response = await listIngestBatches({
    limit: batchLimit, offset: batchOffset.value,
    status: batchStatusFilter.value || undefined,
    parser_backend: batchParserFilter.value || undefined,
    keyword: batchKeyword.value || undefined,
  })
  batches.value = response.items
  batchesTotal.value = response.total
}

async function pollBatches() {
  if (polling) return
  polling = true
  try { await refreshBatches() }
  catch (err) { error.value = err instanceof Error ? err.message : '批次状态刷新失败' }
  finally { polling = false }
}

function elapsed(batch: IngestBatchItem) {
  const end = batch.finished_at ? Date.parse(batch.finished_at) : Date.now()
  const start = Date.parse(batch.started_at ?? batch.created_at)
  if (!Number.isFinite(end - start)) return '—'
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  return seconds >= 60 ? `${Math.floor(seconds / 60)}分${seconds % 60}秒` : `${seconds}秒`
}

function waitTime(batch: IngestBatchItem) {
  if (!batch.started_at) return '排队中'
  const seconds = Math.max(0, Math.round((Date.parse(batch.started_at) - Date.parse(batch.created_at)) / 1000))
  return `${seconds}秒`
}

function applyKeyword() {
  batchKeyword.value = keywordInput.value.trim()
  batchOffset.value = 0
  void pollBatches()
}

function changePage(direction: -1 | 1) {
  batchOffset.value = Math.max(0, batchOffset.value + direction * batchLimit)
  void pollBatches()
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([refreshOverview(), refreshSessionDocs(), refreshBatches()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

watch(sessionStatusFilter, refreshSessionDocs)
watch([batchStatusFilter, batchParserFilter], () => {
  batchOffset.value = 0
  void pollBatches()
})

onMounted(() => { void refresh(); pollTimer = setInterval(() => { void pollBatches() }, 3000) })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>解析监控</h1>
      </div>
      <button type="button" class="ghost-btn" :disabled="loading" @click="refresh">刷新</button>
    </header>

    <p v-if="loading && !overview" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <section class="panel">
      <div class="panel-head"><h2>解析任务（{{ batchesTotal }}）</h2><span class="hint">每 3 秒刷新</span></div>
      <div class="batch-filters">
        <select v-model="batchStatusFilter" class="filter-select" aria-label="按任务状态筛选">
          <option v-for="option in batchStatusOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <select v-model="batchParserFilter" class="filter-select" aria-label="按解析器筛选">
          <option value="">全部解析器</option><option value="docling">Docling</option><option value="mineru">MinerU</option>
        </select>
        <input v-model="keywordInput" class="filter-input" aria-label="搜索任务或文档" placeholder="任务名、任务 ID 或文档 ID" @keyup.enter="applyKeyword" />
        <button type="button" class="filter-btn" @click="applyKeyword">搜索</button>
      </div>
      <p v-if="!batches.length" class="hint">暂无批量解析任务。</p>
      <article v-for="batch in batches" :key="batch.batch_id" class="batch-card">
        <div class="batch-head">
          <div><h3>{{ batch.title }}</h3><span class="mono">{{ batch.batch_id }}</span></div>
          <span :class="statusClass(batch.status)">{{ statusLabel(batch.status) }}</span>
        </div>
        <p class="batch-meta">{{ batch.total_files }} 份 · {{ batch.parser_backend }} · 创建 {{ formatTime(batch.created_at) }} · 排队 {{ waitTime(batch) }} · 总耗时 {{ elapsed(batch) }}</p>
        <div class="batch-counts">
          <span>待处理 {{ batch.counts.pending }}</span><span>处理中 {{ batch.counts.active }}</span>
          <span>完成 {{ batch.counts.done }}</span><span>失败 {{ batch.counts.failed }}</span>
        </div>
        <progress :value="batch.counts.done + batch.counts.failed" :max="batch.total_files" />
        <span class="hint">{{ Math.round((batch.counts.done + batch.counts.failed) * 100 / batch.total_files) }}% 已处理</span>
        <IngestBatchChart :events="batch.events" :total="batch.total_files" :live="batch.status === 'QUEUED' || batch.status === 'RUNNING'" />
        <details><summary>文件阶段与错误明细（{{ batch.files.length }}）</summary>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>文档</th><th>阶段</th><th>更新时间</th><th>失败原因</th></tr></thead>
            <tbody><tr v-for="file in batch.files" :key="file.job_id">
              <td class="mono">{{ file.doc_id }}</td><td><span :class="statusClass(file.status)">{{ statusLabel(file.status) }}</span></td>
              <td>{{ formatTime(file.updated_at) }}</td><td class="error">{{ file.error_message || '—' }}</td>
            </tr></tbody></table></div>
        </details>
      </article>
      <div v-if="batchesTotal > batchLimit" class="pagination">
        <span class="hint">第 {{ batchOffset + 1 }}–{{ Math.min(batchOffset + batchLimit, batchesTotal) }} 条 / 共 {{ batchesTotal }} 条</span>
        <button type="button" :disabled="batchOffset === 0" @click="changePage(-1)">上一页</button>
        <button type="button" :disabled="batchOffset + batchLimit >= batchesTotal" @click="changePage(1)">下一页</button>
      </div>
    </section>

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
          <p class="stat-label">文件处理记录</p>
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

      <div>
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

.batch-filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 12px 0 16px; }
.filter-input { min-width: 220px; flex: 1; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }
.filter-btn, .pagination button { padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); cursor: pointer; }
.pagination { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 14px; }
.pagination button:disabled { opacity: .5; cursor: default; }
.batch-card { border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-top: 14px; }
.batch-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.batch-head h3 { margin: 0 0 4px; font-size: 16px; }
.batch-meta { color: var(--text-muted); font-size: 12px; }
.batch-counts { display: flex; gap: 14px; flex-wrap: wrap; font-size: 13px; margin: 10px 0; }
.batch-card progress { width: 100%; height: 8px; accent-color: #059669; }
.batch-card details { margin-top: 12px; }

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

}
</style>
