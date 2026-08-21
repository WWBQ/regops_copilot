<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  EVAL_STATUS_LABELS,
  RUNNER_LABELS,
  createEvalTask,
  deleteEvalRun,
  deleteEvalTask,
  getEvalRun,
  listEvalRuns,
  listEvalTasks,
  listGoldenSets,
  startEvalRun,
  uploadGoldenSet,
  type EvalRunItem,
  type EvalTask,
  type GoldenSetOption,
} from '../../api/eval'

const tasks = ref<EvalTask[]>([])
const goldenSets = ref<GoldenSetOption[]>([])
const runners = ref<string[]>([])
const selectedTaskId = ref('')
const runs = ref<EvalRunItem[]>([])
const activeRun = ref<EvalRunItem | null>(null)
const loading = ref(true)
const running = ref(false)
const error = ref('')
const debugLimit = ref(0)
const showTaskManager = ref(false)
const uploadFilename = ref('')
const uploadRunner = ref('rag_retrieval')
const uploadStatus = ref('')
const goldenFileInput = ref<HTMLInputElement | null>(null)
const newTask = ref({
  id: '',
  name: '',
  description: '',
  golden_file: '',
  runner: 'rag_retrieval',
})

let pollTimer: ReturnType<typeof setInterval> | null = null

const selectedTask = computed(() => tasks.value.find((t) => t.id === selectedTaskId.value))

const canDeleteSelectedTask = computed(
  () => selectedTask.value != null && !selectedTask.value.builtin,
)

const progressPercent = computed(() => {
  const p = activeRun.value?.progress
  if (!p || !p.total) return 0
  return Math.min(100, Math.round((p.done / p.total) * 100))
})

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

function statusClass(status: string) {
  if (status === 'completed') return 'tag ok'
  if (status === 'running') return 'tag running'
  if (status === 'failed') return 'tag fail'
  return 'tag muted'
}

function formatPercent(value: number | undefined) {
  if (value == null) return '—'
  return `${(value * 100).toFixed(1)}%`
}

async function loadTasks() {
  const response = await listEvalTasks()
  tasks.value = response.items
  if (selectedTaskId.value && !tasks.value.some((t) => t.id === selectedTaskId.value)) {
    selectedTaskId.value = tasks.value[0]?.id ?? ''
  }
  if (!selectedTaskId.value && tasks.value.length) {
    selectedTaskId.value = tasks.value[0].id
  }
}

async function loadGoldenSets() {
  const response = await listGoldenSets()
  goldenSets.value = response.items
  runners.value = response.runners
  if (!newTask.value.golden_file && goldenSets.value.length) {
    newTask.value.golden_file = goldenSets.value[0].filename
  }
}

async function loadRuns() {
  if (!selectedTaskId.value) {
    runs.value = []
    activeRun.value = null
    return
  }
  const response = await listEvalRuns(selectedTaskId.value)
  runs.value = response.items.filter((run) => run.task_id === selectedTaskId.value)
  const currentStillVisible = activeRun.value && runs.value.some((r) => r.run_id === activeRun.value?.run_id)
  if (!currentStillVisible) {
    activeRun.value = runs.value[0] ?? null
    if (activeRun.value?.status === 'running') {
      await refreshActiveRun(activeRun.value.run_id)
    }
  }
}

async function refreshActiveRun(runId: string) {
  activeRun.value = await getEvalRun(runId, true)
}

async function refreshAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadTasks(), loadGoldenSets()])
    await loadRuns()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function onGoldenFileSelected(event: Event) {
  uploadStatus.value = ''
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const content = JSON.parse(text) as Record<string, unknown>
    const itemCount = Array.isArray(content.items) ? content.items.length : 0
    uploadFilename.value = file.name.endsWith('.json') ? file.name : `${file.name}.json`
    uploadStatus.value = `已选择 ${file.name}（${itemCount} 题），点击「上传数据集」保存`
    ;(input as HTMLInputElement & { _parsedContent?: Record<string, unknown> })._parsedContent = content
  } catch {
    uploadStatus.value = ''
    error.value = 'JSON 解析失败，请检查文件格式'
  }
}

async function onUploadGoldenSet() {
  error.value = ''
  uploadStatus.value = ''
  const input = goldenFileInput.value as HTMLInputElement & { _parsedContent?: Record<string, unknown> }
  const content = input?._parsedContent
  if (!content || !uploadFilename.value) {
    error.value = '请先选择 JSON 黄金集文件'
    return
  }
  try {
    const saved = await uploadGoldenSet({
      filename: uploadFilename.value,
      content,
      runner: uploadRunner.value,
    })
    uploadStatus.value = `已上传 ${saved.filename}（${saved.item_count} 题）`
    newTask.value.golden_file = saved.filename
    if (goldenFileInput.value) {
      goldenFileInput.value.value = ''
      delete (goldenFileInput.value as HTMLInputElement & { _parsedContent?: Record<string, unknown> })._parsedContent
    }
    await loadGoldenSets()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
  }
}

async function onCreateTask() {
  error.value = ''
  try {
    const created = await createEvalTask({
      id: newTask.value.id.trim(),
      name: newTask.value.name.trim(),
      description: newTask.value.description.trim(),
      golden_file: newTask.value.golden_file,
      runner: newTask.value.runner,
    })
    newTask.value = { id: '', name: '', description: '', golden_file: goldenSets.value[0]?.filename ?? '', runner: 'rag_retrieval' }
    await loadTasks()
    selectedTaskId.value = created.id
    showTaskManager.value = false
  } catch (err) {
    error.value = err instanceof Error ? err.message : '添加任务失败'
  }
}

async function onDeleteTask() {
  if (!selectedTaskId.value || !canDeleteSelectedTask.value) return
  if (!window.confirm(`确定删除任务「${selectedTask.value?.name}」？`)) return
  error.value = ''
  try {
    await deleteEvalTask(selectedTaskId.value)
    activeRun.value = null
    await refreshAll()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除任务失败'
  }
}

async function onDeleteRun(run: EvalRunItem, event: Event) {
  event.stopPropagation()
  if (run.status === 'running') {
    error.value = '运行中的报告不可删除'
    return
  }
  if (!window.confirm(`确定删除报告 ${run.run_id.slice(-8)}？`)) return
  error.value = ''
  try {
    await deleteEvalRun(run.run_id)
    if (activeRun.value?.run_id === run.run_id) {
      activeRun.value = null
    }
    await loadRuns()
    if (!activeRun.value && runs.value.length) {
      activeRun.value = runs.value[0]
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除报告失败'
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(runId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const row = await getEvalRun(runId, true)
      activeRun.value = row
      if (row.status !== 'running') {
        stopPolling()
        running.value = false
        await loadRuns()
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '轮询失败'
      stopPolling()
      running.value = false
    }
  }, 2000)
}

async function onRunEval() {
  if (!selectedTaskId.value || running.value) return
  running.value = true
  error.value = ''
  try {
    const row = await startEvalRun({
      task_id: selectedTaskId.value,
      limit: debugLimit.value > 0 ? debugLimit.value : 0,
    })
    activeRun.value = row
    await loadRuns()
    startPolling(row.run_id)
  } catch (err) {
    running.value = false
    error.value = err instanceof Error ? err.message : '启动评测失败'
  }
}

async function selectRun(run: EvalRunItem) {
  activeRun.value = run
  if (run.status === 'running') {
    running.value = true
    startPolling(run.run_id)
  } else {
    stopPolling()
    running.value = false
    await refreshActiveRun(run.run_id)
  }
}

const summaryCards = computed(() => {
  const summary = activeRun.value?.summary
  if (!summary) return []
  if (activeRun.value?.task_id === 'rag_retrieval' || selectedTask.value?.runner === 'rag_retrieval') {
    return [
      { label: 'Recall@k', value: formatPercent(summary.recall_at_k) },
      { label: 'MRR', value: summary.mrr?.toFixed(4) ?? '—' },
      { label: '样本数', value: String(summary.count ?? '—') },
    ]
  }
  return [
    { label: '准确率', value: formatPercent(summary.accuracy) },
    { label: '数字错误率', value: formatPercent(summary.number_error_rate) },
    { label: 'P50 延迟', value: summary.latency_p50_ms != null ? `${summary.latency_p50_ms} ms` : '—' },
  ]
})

const resultRows = computed(() => activeRun.value?.report?.results ?? [])

const resultTotal = computed(() => {
  const summary = activeRun.value?.summary
  if (summary?.count != null) return summary.count
  if (summary?.total != null) return summary.total
  return resultRows.value.length
})

const isRagReport = computed(
  () =>
    selectedTask.value?.runner === 'rag_retrieval' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'rag_retrieval',
)

watch(selectedTaskId, async () => {
  stopPolling()
  running.value = false
  activeRun.value = null
  runs.value = []
  await loadRuns()
})

onMounted(refreshAll)
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>评估报告</h1>
        <p>选择评测任务与黄金集，一键运行并在本页查看 Recall@k、准确率等指标。</p>
      </div>
      <div class="head-actions">
        <button type="button" class="ghost-btn" :disabled="loading" @click="refreshAll">刷新</button>
        <button type="button" class="ghost-btn" @click="showTaskManager = !showTaskManager">
          {{ showTaskManager ? '收起任务管理' : '管理任务' }}
        </button>
      </div>
    </header>

    <div v-if="showTaskManager" class="control-card task-manager">
      <h2 class="panel-title">上传黄金集（数据集）</h2>
      <p class="hint">
        选择本地 JSON 文件上传至 <code>eval/golden/</code>。RAG 检索集每题需含
        <code>question</code>、<code>doc_id</code>、<code>gold_pages</code>；可参考
        <code>rag_retrieval_100.json</code>。
      </p>
      <div class="control-row">
        <label class="field">
          <span>JSON 文件</span>
          <input ref="goldenFileInput" class="input" type="file" accept=".json,application/json" @change="onGoldenFileSelected" />
        </label>
        <label class="field field-sm">
          <span>校验 Runner</span>
          <select v-model="uploadRunner" class="select">
            <option v-for="r in runners" :key="r" :value="r">{{ RUNNER_LABELS[r] ?? r }}</option>
          </select>
        </label>
        <button type="button" class="send-btn" @click="onUploadGoldenSet">上传数据集</button>
      </div>
      <p v-if="uploadStatus" class="upload-status">{{ uploadStatus }}</p>

      <h2 class="panel-title section-gap">添加评测任务</h2>
      <p class="hint">将已上传或内置的黄金集绑定到 runner，即可作为新任务运行。</p>
      <div class="control-row">
        <label class="field field-sm">
          <span>任务 ID</span>
          <input v-model="newTask.id" class="input" placeholder="my_rag_smoke" />
        </label>
        <label class="field">
          <span>名称</span>
          <input v-model="newTask.name" class="input" placeholder="我的 RAG 冒烟集" />
        </label>
        <label class="field">
          <span>黄金集</span>
          <select v-model="newTask.golden_file" class="select">
            <option v-for="g in goldenSets" :key="g.filename" :value="g.filename">
              {{ g.filename }}（{{ g.item_count }} 题）
            </option>
          </select>
        </label>
        <label class="field">
          <span>Runner</span>
          <select v-model="newTask.runner" class="select">
            <option v-for="r in runners" :key="r" :value="r">{{ RUNNER_LABELS[r] ?? r }}</option>
          </select>
        </label>
        <button type="button" class="send-btn" @click="onCreateTask">添加任务</button>
      </div>
      <label class="field field-full">
        <span>描述</span>
        <input v-model="newTask.description" class="input" placeholder="可选说明" />
      </label>
      <div class="task-actions">
        <button
          v-if="canDeleteSelectedTask"
          type="button"
          class="danger-btn"
          @click="onDeleteTask"
        >
          删除当前任务
        </button>
        <p v-else class="hint">内置任务（W1 / RAG）不可删除。</p>
      </div>
    </div>

    <div class="control-card">
      <div class="control-row">
        <label class="field">
          <span>评测任务</span>
          <select v-model="selectedTaskId" class="select" :disabled="running">
            <option v-for="task in tasks" :key="task.id" :value="task.id">
              {{ task.name }}（{{ task.item_count }} 题）{{ task.builtin ? '' : ' · 自定义' }}
            </option>
          </select>
        </label>
        <label class="field field-sm">
          <span>调试 limit（0=全量）</span>
          <input v-model.number="debugLimit" class="input" type="number" min="0" :disabled="running" />
        </label>
        <button type="button" class="send-btn" :disabled="running || !selectedTaskId" @click="onRunEval">
          {{ running ? '评测运行中…' : '运行评测' }}
        </button>
      </div>
      <p v-if="selectedTask" class="task-desc">{{ selectedTask.description }}</p>
      <p v-if="selectedTask" class="task-meta">
        黄金集：<code>{{ selectedTask.golden_file }}</code>
        <span v-if="selectedTask.golden_version"> · {{ selectedTask.golden_version }}</span>
      </p>
    </div>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="activeRun?.status === 'running'" class="progress-card">
      <div class="progress-head">
        <span>运行中 {{ activeRun.run_id }}</span>
        <span>{{ activeRun.progress.done }} / {{ activeRun.progress.total }}</span>
      </div>
      <div class="bar"><span class="bar-fill" :style="{ width: `${progressPercent}%` }" /></div>
      <p v-if="activeRun.progress.current_id" class="hint">当前：{{ activeRun.progress.current_id }}</p>
    </div>

    <div class="layout">
      <aside class="history">
        <h2>历史报告</h2>
        <p v-if="!runs.length" class="hint">暂无报告，点击「运行评测」开始。</p>
        <ul v-else class="run-list">
          <li
            v-for="run in runs"
            :key="run.run_id"
            :class="['run-item', { active: activeRun?.run_id === run.run_id }]"
            @click="selectRun(run)"
          >
            <div class="run-top">
              <span :class="statusClass(run.status)">{{ EVAL_STATUS_LABELS[run.status] ?? run.status }}</span>
              <div class="run-actions">
                <span class="mono">{{ run.run_id.slice(-8) }}</span>
                <button
                  type="button"
                  class="icon-btn"
                  title="删除报告"
                  :disabled="run.status === 'running'"
                  @click="onDeleteRun(run, $event)"
                >
                  ×
                </button>
              </div>
            </div>
            <p class="run-time">{{ formatTime(run.started_at) }}</p>
            <p v-if="run.summary?.accuracy != null" class="run-metric">准确率 {{ formatPercent(run.summary.accuracy) }}</p>
            <p v-else-if="run.summary?.recall_at_k != null" class="run-metric">
              Recall@k {{ formatPercent(run.summary.recall_at_k) }}
            </p>
          </li>
        </ul>
      </aside>

      <main v-if="activeRun" class="report">
        <header class="report-head">
          <h2>{{ selectedTask?.name ?? activeRun.task_id }}</h2>
          <span :class="statusClass(activeRun.status)">{{ EVAL_STATUS_LABELS[activeRun.status] }}</span>
        </header>

        <p v-if="activeRun.error" class="error">{{ activeRun.error }}</p>

        <div v-if="activeRun.summary" class="stats">
          <article v-for="card in summaryCards" :key="card.label" class="stat-card">
            <p class="stat-label">{{ card.label }}</p>
            <p class="stat-value">{{ card.value }}</p>
          </article>
        </div>

        <section v-if="activeRun.summary?.by_category && isRagReport" class="section">
          <h3>分题型</h3>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>题型</th>
                  <th>数量</th>
                  <th>Recall@k</th>
                  <th>MRR</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(metrics, cat) in activeRun.summary.by_category" :key="cat">
                  <td>{{ cat }}</td>
                  <td>{{ metrics.count }}</td>
                  <td>{{ formatPercent(metrics.recall_at_k) }}</td>
                  <td>{{ metrics.mrr?.toFixed(4) ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="resultRows.length" class="section">
          <h3>明细（共 {{ resultTotal }} 条，已全部展示）</h3>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>问题</th>
                  <th v-if="isRagReport">Gold 页</th>
                  <th v-if="isRagReport">命中页</th>
                  <th v-if="isRagReport">命中</th>
                  <th v-if="!isRagReport">状态</th>
                  <th v-if="!isRagReport">说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in resultRows" :key="String(row.id)">
                  <td class="mono">{{ row.id }}</td>
                  <td class="question">{{ row.question }}</td>
                  <template v-if="isRagReport">
                    <td class="mono">{{ (row.gold_pages as number[])?.join(', ') }}</td>
                    <td class="mono">{{ (row.retrieved_pages as number[])?.slice(0, 5).join(', ') }}</td>
                    <td>
                      <span :class="row.page_hit_at_k ? 'tag ok' : 'tag fail'">
                        {{ row.page_hit_at_k ? '是' : '否' }}
                      </span>
                    </td>
                  </template>
                  <template v-else>
                    <td><span :class="row.status === 'pass' ? 'tag ok' : 'tag fail'">{{ row.status }}</span></td>
                    <td class="detail">{{ row.detail }}</td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <p v-else-if="activeRun.status === 'completed'" class="hint">报告无明细数据。</p>
      </main>
    </div>
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
  margin-bottom: 16px;
  flex-wrap: wrap;
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
}

.head-actions {
  display: flex;
  gap: 8px;
}

.head-secondary {
  display: none;
}

.section-gap {
  margin-top: 20px;
}

.upload-status {
  margin: 10px 0 0;
  font-size: 13px;
  color: #047857;
}

.panel-title {
  margin: 0 0 8px;
  font-size: 16px;
}

.task-manager {
  margin-bottom: 16px;
}

.field-full {
  min-width: 100%;
  margin-top: 12px;
}

.task-actions {
  margin-top: 12px;
}

.danger-btn {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
  border-radius: 8px;
  padding: 8px 14px;
  cursor: pointer;
}

.run-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.icon-btn {
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
}

.icon-btn:hover:not(:disabled) {
  color: #b91c1c;
}

.icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.control-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 16px;
}

.control-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 280px;
}

.field-sm {
  min-width: 120px;
}

.field span {
  font-size: 12px;
  color: var(--text-muted);
}

.select,
.input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--surface);
}

.task-desc,
.task-meta {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

.progress-card {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 16px;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 8px;
}

.bar {
  height: 8px;
  background: #dbeafe;
  border-radius: 999px;
  overflow: hidden;
}

.bar-fill {
  display: block;
  height: 100%;
  background: #2563eb;
}

.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
}

.history,
.report {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}

.history h2,
.report-head h2 {
  margin: 0 0 12px;
  font-size: 16px;
}

.run-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.run-item {
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
}

.run-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.run-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.run-time,
.run-metric {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.report-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}

.stat-label {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--text-muted);
}

.stat-value {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.section {
  margin-top: 16px;
}

.section h3 {
  margin: 0 0 8px;
  font-size: 14px;
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

.question {
  max-width: 320px;
}

.detail {
  max-width: 220px;
  color: var(--text-muted);
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

.tag.running {
  background: #eff6ff;
  color: #1d4ed8;
}

.tag.fail {
  background: #fef2f2;
  color: #b91c1c;
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
  font-size: 14px;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .stats {
    grid-template-columns: 1fr;
  }
}
</style>
