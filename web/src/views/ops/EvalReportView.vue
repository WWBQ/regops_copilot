<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { getModels } from '../../api/chat'
import {
  EVAL_STATUS_LABELS,
  RUNNER_LABELS,
  createEvalTask,
  deleteEvalRun,
  deleteEvalTask,
  getEvalRun,
  getGoldenSet,
  listEvalRuns,
  listEvalTasks,
  listGoldenSets,
  startEvalRun,
  uploadGoldenSet,
  type EvalRunItem,
  type EvalTask,
  type GoldenItemPreview,
  type GoldenSetOption,
} from '../../api/eval'
import { modelLabel } from '../../utils/models'

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
const availableModels = ref<string[]>([])
const selectedModel = ref('')
const selectedCategories = ref<string[]>([])
const selectedItemIds = ref<string[]>([])
const goldenItems = ref<GoldenItemPreview[]>([])
const goldenCategories = ref<string[]>([])
const itemQuery = ref('')
const showItemPicker = ref(false)
const temperature = ref(0)
const ragTopK = ref(0)
const resultStatusFilter = ref<'all' | 'pass' | 'fail' | 'refuse' | 'miss'>('all')
const resultQuery = ref('')
const resultCategoryFilter = ref('')
const compareLeftId = ref('')
const compareRightId = ref('')
const compareLeft = ref<EvalRunItem | null>(null)
const compareRight = ref<EvalRunItem | null>(null)
const compareLoading = ref(false)
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

const isW1ChatTask = computed(() => selectedTask.value?.runner === 'w1_chat')
const isRagTask = computed(() => selectedTask.value?.runner === 'rag_retrieval')

const completedRuns = computed(() => runs.value.filter((run) => run.status === 'completed'))

const canCompare = computed(
  () => isW1ChatTask.value && completedRuns.value.length >= 2,
)

const filteredGoldenItems = computed(() => {
  const query = itemQuery.value.trim().toLowerCase()
  return goldenItems.value.filter((item) => {
    if (selectedCategories.value.length && !selectedCategories.value.includes(String(item.category))) {
      return false
    }
    if (!query) return true
    return (
      item.id.toLowerCase().includes(query) ||
      item.question.toLowerCase().includes(query) ||
      String(item.category ?? '').toLowerCase().includes(query)
    )
  })
})

const plannedCount = computed(() => {
  let pool = goldenItems.value
  if (selectedCategories.value.length) {
    pool = pool.filter((item) => selectedCategories.value.includes(String(item.category)))
  }
  if (selectedItemIds.value.length) {
    const wanted = new Set(selectedItemIds.value)
    pool = pool.filter((item) => wanted.has(item.id))
  }
  const count = pool.length
  if (debugLimit.value > 0) return Math.min(count, debugLimit.value)
  return count
})

const failedItemIds = computed(() => {
  const rows = activeRun.value?.report?.results ?? []
  return rows
    .filter((row) => {
      if (isRagReport.value) return row.page_hit_at_k !== true
      if (row.status) return row.status !== 'pass'
      return row.passed === false
    })
    .map((row) => String(row.id))
    .filter(Boolean)
})

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

function runModel(run: EvalRunItem | null | undefined): string {
  if (!run) return ''
  const fromParams = run.params?.model
  if (typeof fromParams === 'string' && fromParams.trim()) return fromParams.trim()
  const fromSummary = run.summary?.model
  if (fromSummary) return fromSummary
  const fromResult = run.report?.results?.[0]?.model
  return typeof fromResult === 'string' ? fromResult : ''
}

function runModelLabel(run: EvalRunItem | null | undefined): string {
  const name = runModel(run)
  return name ? modelLabel(name) : '默认模型'
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

async function loadGoldenPreview() {
  const filename = selectedTask.value?.golden_file
  selectedCategories.value = []
  selectedItemIds.value = []
  itemQuery.value = ''
  showItemPicker.value = false
  resultStatusFilter.value = 'all'
  resultQuery.value = ''
  resultCategoryFilter.value = ''
  if (!filename) {
    goldenItems.value = []
    goldenCategories.value = []
    return
  }
  try {
    const preview = await getGoldenSet(filename)
    goldenItems.value = preview.items
    goldenCategories.value = preview.categories
  } catch {
    goldenItems.value = []
    goldenCategories.value = []
  }
}

function toggleCategory(category: string) {
  if (selectedCategories.value.includes(category)) {
    selectedCategories.value = selectedCategories.value.filter((item) => item !== category)
  } else {
    selectedCategories.value = [...selectedCategories.value, category]
  }
}

function toggleItem(id: string) {
  if (selectedItemIds.value.includes(id)) {
    selectedItemIds.value = selectedItemIds.value.filter((item) => item !== id)
  } else {
    selectedItemIds.value = [...selectedItemIds.value, id]
  }
}

function selectVisibleItems() {
  const ids = filteredGoldenItems.value.map((item) => item.id)
  selectedItemIds.value = [...new Set([...selectedItemIds.value, ...ids])]
}

function clearSelectedItems() {
  selectedItemIds.value = []
}

async function loadModels() {
  try {
    const response = await getModels()
    availableModels.value = response.available
    const preferred = response.default || availableModels.value[0] || ''
    if (!selectedModel.value || !availableModels.value.includes(selectedModel.value)) {
      selectedModel.value = preferred
    }
  } catch {
    availableModels.value = []
  }
}

function pickCompareDefaults() {
  const done = completedRuns.value
  if (done.length < 2) {
    compareLeftId.value = ''
    compareRightId.value = ''
    return
  }
  if (
    compareLeftId.value &&
    compareRightId.value &&
    done.some((run) => run.run_id === compareLeftId.value) &&
    done.some((run) => run.run_id === compareRightId.value)
  ) {
    return
  }
  compareLeftId.value = done[0].run_id
  const other =
    done.find((run) => runModel(run) && runModel(run) !== runModel(done[0])) ?? done[1]
  compareRightId.value = other.run_id
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
    const next = runs.value[0] ?? null
    activeRun.value = next
    // 列表接口只返回 summary，不含 results 明细；自动选中后必须再拉一次详情，
    // 否则已完成的报告会显示「报告无明细数据」。
    if (next) {
      await refreshActiveRun(next.run_id)
    }
  }
  pickCompareDefaults()
}

async function refreshActiveRun(runId: string) {
  activeRun.value = await getEvalRun(runId, true)
}

async function refreshAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadTasks(), loadGoldenSets(), loadModels()])
    await loadGoldenPreview()
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
  if (plannedCount.value === 0) {
    error.value = '没有可跑的题目，请调整题型或勾选题号'
    return
  }
  running.value = true
  error.value = ''
  try {
    const row = await startEvalRun({
      task_id: selectedTaskId.value,
      limit: debugLimit.value > 0 ? debugLimit.value : 0,
      model: isW1ChatTask.value ? selectedModel.value : undefined,
      categories: selectedCategories.value,
      item_ids: selectedItemIds.value,
      top_k: isRagTask.value && ragTopK.value > 0 ? ragTopK.value : undefined,
      temperature: isW1ChatTask.value ? temperature.value : undefined,
    })
    activeRun.value = row
    await loadRuns()
    startPolling(row.run_id)
  } catch (err) {
    running.value = false
    error.value = err instanceof Error ? err.message : '启动评测失败'
  }
}

async function onRetryFailed() {
  if (!failedItemIds.value.length) return
  selectedItemIds.value = [...failedItemIds.value]
  selectedCategories.value = []
  debugLimit.value = 0
  await onRunEval()
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

const isComplianceSchemaReport = computed(
  () =>
    selectedTask.value?.runner === 'compliance_schema' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'compliance_schema',
)

const isAsknumReport = computed(
  () =>
    selectedTask.value?.runner === 'w4_asknum' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'w4_asknum',
)

const isNumberCheckReport = computed(
  () =>
    selectedTask.value?.runner === 'w6_number_check' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'w6_number_check',
)

const summaryCards = computed(() => {
  const summary = activeRun.value?.summary
  if (!summary) return []
  if (activeRun.value?.task_id === 'rag_retrieval' || selectedTask.value?.runner === 'rag_retrieval') {
    return [
      { label: 'Recall@k', value: formatPercent(summary.recall_at_k) },
      { label: 'MRR', value: summary.mrr?.toFixed(4) ?? '—' },
      { label: 'nDCG@k', value: summary.ndcg_at_k?.toFixed(4) ?? '—' },
      { label: 'Citation Acc.', value: formatPercent(summary.citation_accuracy) },
      { label: '样本数', value: String(summary.count ?? '—') },
    ]
  }
  if (isGuardReport.value) {
    const cards = [
      { label: '准确率', value: formatPercent(summary.accuracy) },
      { label: '误放行率', value: formatPercent(summary.false_accept_rate) },
      { label: '样本数', value: String(summary.total ?? '—') },
    ]
    if (selectedTask.value?.runner === 'rag_acl' || activeRun.value?.task_id === 'rag_acl') {
      cards.splice(2, 0, { label: '泄露率', value: formatPercent(summary.leak_rate) })
    }
    return cards
  }
  if (isComplianceSchemaReport.value) {
    return [
      { label: '准确率', value: formatPercent(summary.accuracy) },
      { label: '误放行率', value: formatPercent(summary.false_accept_rate) },
      { label: '误拒率', value: formatPercent(summary.false_reject_rate) },
      { label: '理由命中率', value: formatPercent(summary.rule_hit_rate) },
    ]
  }
  if (isAsknumReport.value) {
    return [
      { label: '准确率', value: formatPercent(summary.accuracy) },
      { label: '路由准确率', value: formatPercent(summary.route_accuracy) },
      { label: '数字泄露率', value: formatPercent(summary.leak_rate) },
      { label: '样本数', value: String(summary.total ?? '—') },
    ]
  }
  if (isNumberCheckReport.value) {
    return [
      { label: '准确率', value: formatPercent(summary.accuracy) },
      { label: '误放行率', value: formatPercent(summary.false_accept_rate) },
      { label: '数字错误率', value: formatPercent(summary.number_error_rate) },
      { label: '量纲错误率', value: formatPercent(summary.unit_error_rate) },
    ]
  }
  if (isStrategyReport.value) {
    const rates = Object.values(summary.by_strategy ?? {}).map((row) => row.number_error_rate ?? 0)
    const maxErr = rates.length ? Math.max(...rates) : summary.number_error_rate
    return [
      { label: '样本 n', value: String(summary.n ?? summary.total ?? '—') },
      { label: 'Zero-shot 准确率', value: formatPercent(summary.by_strategy?.zero_shot?.accuracy ?? summary.accuracy) },
      { label: '最高数字错误率', value: formatPercent(maxErr) },
      { label: '种子', value: summary.seed != null ? String(summary.seed) : '—' },
    ]
  }
  if (isAbReport.value) {
    return [
      { label: 'A 准确率', value: formatPercent(summary.accuracy_a) },
      { label: 'B 准确率', value: formatPercent(summary.accuracy_b) },
      { label: 'Δ', value: formatPercent(summary.delta) },
      { label: '可信？', value: summary.credible ? '是' : '否' },
    ]
  }
  return [
    { label: '模型', value: runModelLabel(activeRun.value) },
    { label: '准确率', value: formatPercent(summary.accuracy) },
    { label: '拒答率', value: formatPercent(summary.refuse_rate) },
    { label: 'P50 延迟', value: summary.latency_p50_ms != null ? `${summary.latency_p50_ms} ms` : '—' },
  ]
})

const resultRows = computed(() => activeRun.value?.report?.results ?? [])

const filteredResultRows = computed(() => {
  const query = resultQuery.value.trim().toLowerCase()
  return resultRows.value.filter((row) => {
    if (resultCategoryFilter.value && String(row.category ?? '') !== resultCategoryFilter.value) {
      return false
    }
    if (resultStatusFilter.value === 'pass') {
      if (isRagReport.value) {
        if (row.page_hit_at_k !== true) return false
      } else if (row.status) {
        if (row.status !== 'pass') return false
      } else if (row.passed !== true) {
        return false
      }
    }
    if (resultStatusFilter.value === 'fail') {
      if (isRagReport.value) {
        if (row.page_hit_at_k !== false) return false
      } else if (row.status) {
        if (row.status !== 'fail') return false
      } else if (row.passed !== false) {
        return false
      }
    }
    if (resultStatusFilter.value === 'refuse' && row.status !== 'refuse') return false
    if (resultStatusFilter.value === 'miss') {
      const failed = isRagReport.value
        ? row.page_hit_at_k !== true
        : row.status
          ? row.status !== 'pass'
          : row.passed === false
      if (!failed) return false
    }
    if (!query) return true
    return (
      String(row.id ?? '').toLowerCase().includes(query) ||
      String(row.question ?? '').toLowerCase().includes(query) ||
      String(row.detail ?? '').toLowerCase().includes(query)
    )
  })
})

const isRagReport = computed(
  () =>
    selectedTask.value?.runner === 'rag_retrieval' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'rag_retrieval',
)

const isGuardReport = computed(() => {
  const runner =
    selectedTask.value?.runner ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner
  return runner === 'rag_acl' || runner === 'rag_refuse'
})

const isW1ChatReport = computed(
  () =>
    selectedTask.value?.runner === 'w1_chat' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'w1_chat',
)

const isStrategyReport = computed(
  () =>
    selectedTask.value?.runner === 'w8_strategy' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'w8_strategy',
)

const isAbReport = computed(
  () =>
    selectedTask.value?.runner === 'w8_ab' ||
    tasks.value.find((t) => t.id === activeRun.value?.task_id)?.runner === 'w8_ab',
)

const strategyRows = computed(() => {
  const raw = activeRun.value?.summary?.by_strategy
  if (!raw) return []
  const labels: Record<string, string> = {
    zero_shot: 'Zero-shot',
    few_shot: 'Few-shot',
    cot: 'CoT',
  }
  return Object.entries(raw).map(([key, metrics]) => ({
    key,
    label: labels[key] ?? key,
    accuracy: metrics.accuracy,
    number_error_rate: metrics.number_error_rate,
    avg_tokens: metrics.avg_tokens,
    latency_p50_ms: metrics.latency_p50_ms,
  }))
})

const compareRows = computed(() => {
  const leftResults = compareLeft.value?.report?.results ?? []
  const rightResults = compareRight.value?.report?.results ?? []
  if (!leftResults.length || !rightResults.length) return []
  const rightById = new Map(rightResults.map((row) => [String(row.id), row]))
  return leftResults.map((left) => {
    const right = rightById.get(String(left.id))
    const leftStatus = String(left.status ?? '')
    const rightStatus = right ? String(right.status ?? '') : ''
    return {
      id: String(left.id),
      question: String(left.question ?? ''),
      category: String(left.category ?? ''),
      leftStatus,
      rightStatus,
      agree: Boolean(right) && leftStatus === rightStatus,
    }
  })
})

const compareDisagreeCount = computed(
  () => compareRows.value.filter((row) => !row.agree).length,
)

watch(selectedTaskId, async () => {
  stopPolling()
  running.value = false
  activeRun.value = null
  runs.value = []
  compareLeftId.value = ''
  compareRightId.value = ''
  compareLeft.value = null
  compareRight.value = null
  await loadGoldenPreview()
  await loadRuns()
})

watch([compareLeftId, compareRightId], async ([left, right]) => {
  if (!left || !right || left === right) {
    compareLeft.value = null
    compareRight.value = null
    return
  }
  compareLoading.value = true
  try {
    const [a, b] = await Promise.all([getEvalRun(left, true), getEvalRun(right, true)])
    compareLeft.value = a
    compareRight.value = b
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载对比报告失败'
    compareLeft.value = null
    compareRight.value = null
  } finally {
    compareLoading.value = false
  }
})

onMounted(refreshAll)
onBeforeUnmount(stopPolling)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>评估报告</h1>
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
        <label v-if="isW1ChatTask" class="field field-sm">
          <span>模型</span>
          <select v-model="selectedModel" class="select" :disabled="running || !availableModels.length">
            <option v-if="!availableModels.length" value="">无可用模型</option>
            <option v-for="name in availableModels" :key="name" :value="name">
              {{ modelLabel(name) }}
            </option>
          </select>
        </label>
        <label v-if="isW1ChatTask" class="field field-sm">
          <span>温度</span>
          <input
            v-model.number="temperature"
            class="input"
            type="number"
            min="0"
            max="2"
            step="0.1"
            :disabled="running"
          />
        </label>
        <label v-if="isRagTask" class="field field-sm">
          <span>top_k（0=默认）</span>
          <input v-model.number="ragTopK" class="input" type="number" min="0" max="50" :disabled="running" />
        </label>
        <label class="field field-sm">
          <span>最多 N 题（0=不截）</span>
          <input v-model.number="debugLimit" class="input" type="number" min="0" :disabled="running" />
        </label>
        <button
          type="button"
          class="send-btn"
          :disabled="running || !selectedTaskId || plannedCount === 0 || (isW1ChatTask && !selectedModel)"
          @click="onRunEval"
        >
          {{ running ? '评测运行中…' : `运行 ${plannedCount} 题` }}
        </button>
      </div>
      <p v-if="selectedTask" class="task-desc">{{ selectedTask.description }}</p>
      <p v-if="selectedTask" class="task-meta">
        黄金集：<code>{{ selectedTask.golden_file }}</code>
        <span v-if="selectedTask.golden_version"> · {{ selectedTask.golden_version }}</span>
        <span v-if="isW1ChatTask && selectedModel"> · {{ modelLabel(selectedModel) }} · 温度 {{ temperature }}</span>
      </p>

      <div v-if="goldenCategories.length" class="chip-row">
        <span class="chip-label">题型</span>
        <button
          type="button"
          class="chip"
          :class="{ on: selectedCategories.length === 0 }"
          :disabled="running"
          @click="selectedCategories = []"
        >
          全部
        </button>
        <button
          v-for="cat in goldenCategories"
          :key="cat"
          type="button"
          class="chip"
          :class="{ on: selectedCategories.includes(cat) }"
          :disabled="running"
          @click="toggleCategory(cat)"
        >
          {{ cat }}
        </button>
      </div>

      <div class="picker-toolbar">
        <button type="button" class="ghost-btn" :disabled="running" @click="showItemPicker = !showItemPicker">
          {{ showItemPicker ? '收起选题' : '选题 / 搜索' }}
        </button>
        <button
          v-if="failedItemIds.length"
          type="button"
          class="ghost-btn"
          :disabled="running"
          @click="onRetryFailed"
        >
          重跑未通过（{{ failedItemIds.length }}）
        </button>
        <span class="hint">未选题号时按题型筛选后全跑；勾选后只跑勾中的题。</span>
      </div>

      <div v-if="showItemPicker" class="item-picker">
        <div class="control-row">
          <label class="field">
            <span>搜索题号 / 题面</span>
            <input v-model="itemQuery" class="input" placeholder="例如 ROE、w1-019、不良" :disabled="running" />
          </label>
          <button type="button" class="ghost-btn" :disabled="running" @click="selectVisibleItems">勾选当前筛选</button>
          <button type="button" class="ghost-btn" :disabled="running || !selectedItemIds.length" @click="clearSelectedItems">
            清空勾选
          </button>
        </div>
        <div class="item-list">
          <label v-for="item in filteredGoldenItems" :key="item.id" class="item-row">
            <input
              type="checkbox"
              :checked="selectedItemIds.includes(item.id)"
              :disabled="running"
              @change="toggleItem(item.id)"
            />
            <span class="mono">{{ item.id }}</span>
            <span class="item-cat">{{ item.category }}</span>
            <span class="item-q">{{ item.question }}</span>
          </label>
          <p v-if="!filteredGoldenItems.length" class="hint">没有匹配的题目。</p>
        </div>
      </div>
    </div>

    <div v-if="canCompare" class="control-card">
      <h2 class="panel-title">对比两份报告</h2>
      <div class="control-row">
        <label class="field">
          <span>报告 A</span>
          <select v-model="compareLeftId" class="select">
            <option v-for="run in completedRuns" :key="run.run_id" :value="run.run_id">
              {{ runModelLabel(run) }} · {{ formatTime(run.started_at) }}
              <template v-if="run.summary?.accuracy != null">
                · 准确率 {{ formatPercent(run.summary.accuracy) }}
              </template>
            </option>
          </select>
        </label>
        <label class="field">
          <span>报告 B</span>
          <select v-model="compareRightId" class="select">
            <option v-for="run in completedRuns" :key="run.run_id" :value="run.run_id">
              {{ runModelLabel(run) }} · {{ formatTime(run.started_at) }}
              <template v-if="run.summary?.accuracy != null">
                · 准确率 {{ formatPercent(run.summary.accuracy) }}
              </template>
            </option>
          </select>
        </label>
      </div>
      <p v-if="compareLeftId && compareLeftId === compareRightId" class="hint">请选两份不同的报告。</p>
      <p v-else-if="compareLoading" class="hint">正在加载对照明细…</p>
      <div v-else-if="compareRows.length" class="compare-block">
        <div class="stats compare-stats">
          <article class="stat-card">
            <p class="stat-label">{{ runModelLabel(compareLeft) }} 准确率</p>
            <p class="stat-value">{{ formatPercent(compareLeft?.summary?.accuracy) }}</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">{{ runModelLabel(compareRight) }} 准确率</p>
            <p class="stat-value">{{ formatPercent(compareRight?.summary?.accuracy) }}</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">{{ runModelLabel(compareLeft) }} 拒答率</p>
            <p class="stat-value">{{ formatPercent(compareLeft?.summary?.refuse_rate) }}</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">{{ runModelLabel(compareRight) }} 拒答率</p>
            <p class="stat-value">{{ formatPercent(compareRight?.summary?.refuse_rate) }}</p>
          </article>
          <article class="stat-card">
            <p class="stat-label">逐题不一致</p>
            <p class="stat-value">{{ compareDisagreeCount }} / {{ compareRows.length }}</p>
          </article>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>题型</th>
                <th>问题</th>
                <th>{{ runModelLabel(compareLeft) }}</th>
                <th>{{ runModelLabel(compareRight) }}</th>
                <th>对照</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in compareRows" :key="row.id" :class="{ disagree: !row.agree }">
                <td class="mono">{{ row.id }}</td>
                <td>{{ row.category }}</td>
                <td class="question">{{ row.question }}</td>
                <td><span :class="row.leftStatus === 'pass' ? 'tag ok' : row.leftStatus === 'refuse' ? 'tag muted' : 'tag fail'">{{ row.leftStatus || '—' }}</span></td>
                <td><span :class="row.rightStatus === 'pass' ? 'tag ok' : row.rightStatus === 'refuse' ? 'tag muted' : 'tag fail'">{{ row.rightStatus || '—' }}</span></td>
                <td>{{ row.agree ? '一致' : '不一致' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
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
            <p v-if="runModel(run)" class="run-metric">{{ runModelLabel(run) }}</p>
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
          <div class="report-head-actions">
            <button
              v-if="failedItemIds.length && activeRun.status === 'completed'"
              type="button"
              class="ghost-btn"
              :disabled="running"
              @click="onRetryFailed"
            >
              重跑未通过（{{ failedItemIds.length }}）
            </button>
            <span :class="statusClass(activeRun.status)">{{ EVAL_STATUS_LABELS[activeRun.status] }}</span>
          </div>
        </header>

        <p v-if="activeRun.error" class="error">{{ activeRun.error }}</p>

        <div v-if="activeRun.summary" class="stats">
          <article v-for="card in summaryCards" :key="card.label" class="stat-card">
            <p class="stat-label">{{ card.label }}</p>
            <p class="stat-value">{{ card.value }}</p>
          </article>
        </div>

        <p v-if="isAbReport && activeRun.summary?.verdict" class="hint">{{ activeRun.summary.verdict }}</p>

        <section v-if="isStrategyReport && strategyRows.length" class="section">
          <h3>三策略对照</h3>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>策略</th>
                  <th>准确率</th>
                  <th>数字错误率</th>
                  <th>均 Token</th>
                  <th>P50 延迟</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in strategyRows" :key="row.key">
                  <td>{{ row.label }}</td>
                  <td>{{ formatPercent(row.accuracy) }}</td>
                  <td>{{ formatPercent(row.number_error_rate) }}</td>
                  <td>{{ row.avg_tokens != null ? Math.round(row.avg_tokens) : '—' }}</td>
                  <td>{{ row.latency_p50_ms != null ? `${Math.round(row.latency_p50_ms)} ms` : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <ul v-if="activeRun.summary?.when_not_worth?.length" class="hint-list">
            <li v-for="note in activeRun.summary.when_not_worth" :key="`${note.strategy}-${note.when}`">
              <strong>{{ note.strategy }}</strong>
              · {{ note.when }}：{{ note.reason }}
            </li>
          </ul>
        </section>

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
                  <th>nDCG@k</th>
                  <th>Citation Acc.</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(metrics, cat) in activeRun.summary.by_category"
                  :key="cat"
                  class="clickable"
                  @click="resultCategoryFilter = resultCategoryFilter === String(cat) ? '' : String(cat)"
                >
                  <td>{{ cat }}</td>
                  <td>{{ metrics.count }}</td>
                  <td>{{ formatPercent(metrics.recall_at_k) }}</td>
                  <td>{{ metrics.mrr?.toFixed(4) ?? '—' }}</td>
                  <td>{{ metrics.ndcg_at_k?.toFixed(4) ?? '—' }}</td>
                  <td>{{ formatPercent(metrics.citation_accuracy) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="activeRun.summary?.by_category && (isAsknumReport || isNumberCheckReport || isStrategyReport || isAbReport || isGuardReport)" class="section">
          <h3>分题型</h3>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>题型</th>
                  <th>数量</th>
                  <th>通过</th>
                  <th>失败</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(metrics, cat) in activeRun.summary.by_category"
                  :key="cat"
                  class="clickable"
                  @click="resultCategoryFilter = resultCategoryFilter === String(cat) ? '' : String(cat)"
                >
                  <td>{{ cat }}</td>
                  <td>{{ metrics.total }}</td>
                  <td>{{ metrics.passed }}</td>
                  <td>{{ metrics.failed }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="activeRun.summary?.by_category && isW1ChatReport" class="section">
          <h3>分题型</h3>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>题型</th>
                  <th>数量</th>
                  <th>准确率</th>
                  <th>拒答</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(metrics, cat) in activeRun.summary.by_category"
                  :key="cat"
                  class="clickable"
                  @click="resultCategoryFilter = resultCategoryFilter === String(cat) ? '' : String(cat)"
                >
                  <td>{{ cat }}</td>
                  <td>{{ metrics.total ?? metrics.count }}</td>
                  <td>{{ formatPercent(metrics.accuracy) }}</td>
                  <td>{{ metrics.refused ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="resultRows.length" class="section">
          <h3>明细（{{ filteredResultRows.length }} / {{ resultRows.length }}）</h3>
          <div class="control-row result-filters">
            <label class="field field-sm">
              <span>结果</span>
              <select v-model="resultStatusFilter" class="select">
                <option value="all">全部</option>
                <option value="miss">未通过</option>
                <option value="pass">通过</option>
                <option value="fail">失败</option>
                <option v-if="isW1ChatReport" value="refuse">拒答</option>
              </select>
            </label>
            <label class="field field-sm">
              <span>题型</span>
              <select v-model="resultCategoryFilter" class="select">
                <option value="">全部</option>
                <option v-for="cat in Object.keys(activeRun.summary?.by_category ?? {})" :key="cat" :value="cat">
                  {{ cat }}
                </option>
              </select>
            </label>
            <label class="field">
              <span>搜索</span>
              <input v-model="resultQuery" class="input" placeholder="题号 / 题面 / 判分说明" />
            </label>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <template v-if="isComplianceSchemaReport">
                    <th>规则</th>
                    <th>期望</th>
                    <th>实际</th>
                    <th>结果</th>
                    <th>说明</th>
                  </template>
                  <template v-else>
                    <th>问题</th>
                    <th v-if="isW1ChatReport || isAsknumReport || isNumberCheckReport || isStrategyReport || isAbReport || isGuardReport">题型</th>
                    <th v-if="isRagReport">Gold 页</th>
                    <th v-if="isRagReport">命中页</th>
                    <th v-if="isRagReport">命中</th>
                    <th v-if="isRagReport">nDCG</th>
                    <th v-if="isRagReport">引用准确</th>
                    <th v-if="isGuardReport">部门</th>
                    <th v-if="isGuardReport">期望</th>
                    <th v-if="isGuardReport">实际</th>
                    <th v-if="!isRagReport">状态</th>
                    <th v-if="!isRagReport">说明</th>
                  </template>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in filteredResultRows" :key="String(row.id)">
                  <td class="mono">{{ row.id }}</td>
                  <template v-if="isComplianceSchemaReport">
                    <td class="mono">{{ row.rule }}</td>
                    <td>{{ row.expected === 'accept' ? '放行' : '拒绝' }}</td>
                    <td>{{ row.actual === 'accept' ? '放行' : '拒绝' }}</td>
                    <td>
                      <span :class="row.passed ? 'tag ok' : 'tag fail'">
                        {{ row.passed ? '通过' : '失败' }}
                      </span>
                    </td>
                    <td class="detail">{{ row.detail }}</td>
                  </template>
                  <template v-else>
                    <td class="question">{{ row.question }}</td>
                    <td v-if="isW1ChatReport || isAsknumReport || isNumberCheckReport || isStrategyReport || isAbReport || isGuardReport">{{ row.category }}</td>
                    <template v-if="isRagReport">
                      <td class="mono">{{ (row.gold_pages as number[])?.join(', ') }}</td>
                      <td class="mono">{{ (row.retrieved_pages as number[])?.slice(0, 5).join(', ') }}</td>
                      <td>
                        <span :class="row.page_hit_at_k ? 'tag ok' : 'tag fail'">
                          {{ row.page_hit_at_k ? '是' : '否' }}
                        </span>
                      </td>
                      <td class="mono">{{ typeof row.ndcg_at_k === 'number' ? row.ndcg_at_k.toFixed(4) : '—' }}</td>
                      <td class="mono">{{ formatPercent(row.citation_accuracy as number | undefined) }}</td>
                    </template>
                    <template v-else-if="isGuardReport">
                      <td class="mono">{{ row.dept == null || row.dept === '' ? '（未登录）' : String(row.dept) }}</td>
                      <td class="mono">{{ row.expected_outcome }}</td>
                      <td class="mono">{{ row.actual_outcome }}</td>
                      <td>
                        <span :class="row.passed ? 'tag ok' : 'tag fail'">
                          {{ row.passed ? '通过' : '失败' }}
                        </span>
                      </td>
                      <td class="detail">
                        期望 {{ Array.isArray(row.expected_companies) ? (row.expected_companies as string[]).join(',') || '—' : '—' }}
                        · 实际 {{ Array.isArray(row.actual_companies) ? (row.actual_companies as string[]).join(',') || '—' : '—' }}
                        <template v-if="Array.isArray(row.leaked_companies) && row.leaked_companies.length">
                          · 泄露 {{ (row.leaked_companies as string[]).join(',') }}
                        </template>
                      </td>
                    </template>
                    <template v-else>
                      <td>
                        <span
                          :class="
                            row.status === 'pass'
                              ? 'tag ok'
                              : row.status === 'refuse'
                                ? 'tag muted'
                                : 'tag fail'
                          "
                        >{{ row.status }}</span>
                      </td>
                      <td class="detail">{{ row.detail }}</td>
                    </template>
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

.report-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}

.chip-label {
  font-size: 12px;
  color: var(--text-muted);
}

.chip {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.chip.on {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.picker-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}

.item-picker {
  margin-top: 10px;
}

.item-list {
  max-height: 240px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-top: 8px;
}

.item-row {
  display: grid;
  grid-template-columns: auto 88px 120px 1fr;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.item-cat {
  color: var(--text-muted);
  font-size: 12px;
}

.item-q {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clickable {
  cursor: pointer;
}

.clickable:hover td {
  background: #f8fafc;
}

.result-filters {
  margin-bottom: 8px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.compare-block {
  margin-top: 12px;
}

.compare-stats {
  margin-bottom: 12px;
}

tr.disagree td {
  background: #fff7ed;
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

.hint-list {
  margin: 12px 0 0;
  padding-left: 18px;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
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
