<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { formatUserFacingError } from '../../api/client'
import {
  getAgentRunTrace, listAgentRuns,
  type AgentRunItem, type AgentRunListResponse, type AgentRunTrace, type AgentTraceEvent,
} from '../../api/riskAgent'

const PAGE_SIZE = 30
const lanes: AgentTraceEvent['phase'][] = ['model', 'tool', 'subagent']
const data = ref<AgentRunListResponse | null>(null)
const trace = ref<AgentRunTrace | null>(null)
const selectedRunId = ref('')
const selectedThreadId = ref('')
const offset = ref(0)
const loading = ref(false)
const loadingTrace = ref(false)
const error = ref('')
const traceError = ref('')
const query = ref('')
const tab = ref<'time' | 'events' | 'tools'>('time')
let traceRequest = 0

const visibleEvents = computed(() => {
  const text = query.value.trim().toLowerCase()
  return (trace.value?.events ?? []).filter((event) =>
    (tab.value !== 'tools' || event.phase === 'tool') &&
    (!text || `${event.phase} ${event.label} ${event.status}`.toLowerCase().includes(text)),
  )
})
const toolCount = computed(() => (trace.value?.events ?? []).filter((event) => event.phase === 'tool').length)
const modelCount = computed(() => (trace.value?.events ?? []).filter((event) => event.phase === 'model').length)

async function selectRun(row: AgentRunItem) {
  selectedRunId.value = row.run_id
  trace.value = null
  traceError.value = ''
  loadingTrace.value = true
  const request = ++traceRequest
  try {
    const result = await getAgentRunTrace(row.run_id)
    if (request === traceRequest) trace.value = result
  } catch (err) {
    if (request === traceRequest) traceError.value = formatUserFacingError(err)
  } finally {
    if (request === traceRequest) loadingTrace.value = false
  }
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const result = await listAgentRuns(PAGE_SIZE, offset.value, selectedThreadId.value || null)
    data.value = result
    const selected = result.items.find((item) => item.run_id === selectedRunId.value) ?? result.items[0]
    if (selected) await selectRun(selected)
    else { selectedRunId.value = ''; trace.value = null }
  } catch (err) {
    error.value = formatUserFacingError(err)
  } finally {
    loading.value = false
  }
}

function goTo(next: number) { offset.value = next; void refresh() }

function changeSession() {
  offset.value = 0
  selectedRunId.value = ''
  trace.value = null
  void refresh()
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN')
}

function formatDuration(value: number | null | undefined): string {
  if (value == null) return '—'
  return value < 1000 ? `${Math.max(0, Math.round(value))} ms` : `${(value / 1000).toFixed(1)} s`
}

function eventDuration(event: AgentTraceEvent): string {
  if (!event.finished_at) return event.status === 'running' ? '进行中' : '—'
  return formatDuration(new Date(event.finished_at).getTime() - new Date(event.started_at).getTime())
}

function eventPosition(event: AgentTraceEvent): { left: string; width: string } {
  if (!trace.value) return { left: '0%', width: '2%' }
  const start = new Date(trace.value.started_at).getTime()
  const end = new Date(trace.value.finished_at ?? new Date().toISOString()).getTime()
  const span = Math.max(end - start, 1)
  const eventStart = new Date(event.started_at).getTime()
  const eventEnd = new Date(event.finished_at ?? trace.value.finished_at ?? new Date().toISOString()).getTime()
  const left = Math.max(0, Math.min(98, ((eventStart - start) / span) * 100))
  const width = Math.max(1.5, Math.min(100 - left, ((eventEnd - eventStart) / span) * 100))
  return { left: `${left}%`, width: `${width}%` }
}

function phaseLabel(phase: AgentTraceEvent['phase']): string {
  return { user: '用户', model: '模型', tool: '工具', subagent: '子 Agent' }[phase]
}

function statusLabel(status: string): string {
  return { completed: '已完成', failed: '失败', running: '运行中' }[status] ?? status
}

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div><h1>Agent 监控</h1><p>按运行查看真实发生的模型输出、工具调用和耗时</p></div>
      <button type="button" class="refresh-btn" :disabled="loading" @click="refresh">刷新</button>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="data" class="stats">
      <article><span>运行总数</span><strong>{{ data.total }}</strong></article>
      <article><span>已完成</span><strong>{{ data.summary.completed }}</strong></article>
      <article><span>运行中</span><strong>{{ data.summary.running }}</strong></article>
      <article><span>失败</span><strong>{{ data.summary.failed }}</strong></article>
      <article><span>平均耗时</span><strong>{{ data.total ? formatDuration(data.summary.avg_duration_ms) : '—' }}</strong></article>
    </div>

    <div v-if="data" class="session-filter">
      <label for="agent-session-filter">会话</label>
      <select id="agent-session-filter" v-model="selectedThreadId" :disabled="loading" @change="changeSession">
        <option value="">全部会话</option>
        <option v-for="session in data.sessions" :key="session.thread_id" :value="session.thread_id">
          {{ session.title }}（{{ session.run_count }} 次运行）
        </option>
      </select>
    </div>

    <div v-if="data" class="layout">
      <aside class="runs" aria-label="运行记录">
        <div class="runs-head">运行记录 <span>{{ data.total }}</span></div>
        <p v-if="!data.items.length" class="empty-run">暂无 Agent 运行记录</p>
        <button v-for="row in data.items" :key="row.run_id" type="button" class="run-item"
          :class="{ selected: selectedRunId === row.run_id }" @click="selectRun(row)">
          <span class="run-title">{{ row.title }}</span>
          <span v-if="!selectedThreadId" class="run-session">会话：{{ row.session_title }}</span>
          <span class="run-meta"><span :class="['dot', row.status]"></span>{{ statusLabel(row.status) }} · {{ formatDuration(row.duration_ms) }}</span>
          <time>{{ formatTime(row.started_at) }}</time>
        </button>
        <div v-if="data.total > PAGE_SIZE" class="pagination">
          <button type="button" :disabled="loading || offset === 0" @click="goTo(Math.max(0, offset - PAGE_SIZE))">上一页</button>
          <span>{{ offset + 1 }}–{{ Math.min(offset + PAGE_SIZE, data.total) }} / {{ data.total }}</span>
          <button type="button" :disabled="loading || offset + PAGE_SIZE >= data.total" @click="goTo(offset + PAGE_SIZE)">下一页</button>
        </div>
      </aside>

      <div class="trace">
        <p v-if="loadingTrace" class="trace-state">加载运行轨迹…</p>
        <p v-else-if="traceError" class="trace-state alert" role="alert">{{ traceError }}</p>
        <template v-else-if="trace">
          <header class="trace-head">
            <div><span class="eyebrow">RUN TRACE</span><h2>{{ trace.title }}</h2>
              <p>会话：{{ trace.session_title }} · {{ formatTime(trace.started_at) }} · {{ statusLabel(trace.status) }}</p></div>
            <div class="trace-totals"><span>{{ modelCount }} 个模型输出事件</span><span>{{ toolCount }} 次工具调用</span></div>
          </header>
          <div class="trace-toolbar">
            <div class="tabs" role="tablist" aria-label="轨迹视图">
              <button type="button" role="tab" :aria-selected="tab === 'time'" :class="{ active: tab === 'time' }" @click="tab = 'time'">时长</button>
              <button type="button" role="tab" :aria-selected="tab === 'events'" :class="{ active: tab === 'events' }" @click="tab = 'events'">事件</button>
              <button type="button" role="tab" :aria-selected="tab === 'tools'" :class="{ active: tab === 'tools' }" @click="tab = 'tools'">调用</button>
            </div>
            <input v-model="query" type="search" aria-label="搜索轨迹事件" placeholder="搜索事件或工具" />
          </div>
          <div v-if="tab === 'time' && trace.events.length" class="timeline" aria-label="运行时间线">
            <div v-for="phase in lanes" :key="phase" class="lane">
              <span class="lane-label">{{ phaseLabel(phase) }}</span>
              <div class="lane-track"><span v-for="event in visibleEvents.filter((item) => item.phase === phase)" :key="event.id"
                class="lane-bar" :class="phase" :style="eventPosition(event)" :title="`${event.label} · ${eventDuration(event)}`"></span></div>
            </div>
          </div>
          <p v-if="trace.error" class="trace-failure">运行失败：{{ trace.error }}</p>
          <p v-if="!trace.events.length" class="trace-state">这次运行没有详细轨迹。历史运行无法补录已丢失的模型和工具事件，请发起新任务后查看。</p>
          <p v-else-if="!visibleEvents.length" class="trace-state">没有匹配的事件。</p>
          <ol v-else class="events">
            <li v-for="event in visibleEvents" :key="event.id" class="event-row">
              <span :class="['phase-tag', event.phase]">{{ phaseLabel(event.phase) }}</span>
              <span class="event-label">{{ event.label }}</span>
              <span class="event-status" :class="event.status">{{ statusLabel(event.status) }}</span>
              <span class="event-duration">{{ eventDuration(event) }}</span>
              <time class="event-time">{{ formatTime(event.started_at) }}</time>
            </li>
          </ol>
          <p class="trace-note">时间线记录模型输出阶段和实际工具生命周期，不等同于完整模型推理耗时。原始工具参数和模型正文不会写入监控轨迹。</p>
        </template>
        <p v-else class="trace-state">选择左侧运行记录查看轨迹。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page { width: 100%; max-width: 1500px; }
.head { display: flex; justify-content: space-between; align-items: start; gap: 16px; margin-bottom: 18px; }
.head h1 { margin: 0; font-size: 24px; color: var(--text-strong); }.head p { margin: 7px 0 0; font-size: 13px; color: var(--muted); }
.refresh-btn, .pagination button { border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text-strong); padding: 8px 14px; cursor: pointer; } button:disabled { opacity: .5; cursor: not-allowed; }
.stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }.stats article { padding: 14px 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); display: flex; flex-direction: column; gap: 7px; }.stats span { font-size: 12px; color: var(--muted); }.stats strong { font-size: 22px; color: var(--text-strong); }
.session-filter { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; color: var(--muted); font-size: 13px; }.session-filter select { min-width: 260px; max-width: min(520px, 100%); padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text-strong); }
.layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 14px; align-items: start; }.runs { background: var(--surface); border: 1px solid var(--border); border-radius: 13px; overflow: hidden; }.runs-head { padding: 13px 15px; border-bottom: 1px solid var(--border); font-weight: 650; display: flex; justify-content: space-between; }.runs-head span { color: var(--muted); font-weight: 400; }.empty-run { padding: 16px; color: var(--muted); }
.run-item { display: flex; width: 100%; flex-direction: column; text-align: left; gap: 6px; background: transparent; color: var(--text-strong); border: 0; border-bottom: 1px solid var(--border); padding: 13px 15px; cursor: pointer; }.run-item:hover, .run-item.selected { background: #eef6ff; }.run-item.selected { box-shadow: inset 3px 0 #3b82f6; }.run-title { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; }.run-meta, .run-session, .run-item time { font-size: 12px; color: var(--muted); }.run-session { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; }.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #eab308; margin-right: 6px; }.dot.completed { background: #22c55e; }.dot.failed { background: #ef4444; }.pagination { display: flex; justify-content: space-between; align-items: center; gap: 5px; padding: 9px; color: var(--muted); font-size: 11px; }.pagination button { padding: 5px 8px; }
.trace { min-width: 0; min-height: 370px; background: #1b1c20; color: #e5e7eb; border-radius: 13px; border: 1px solid #34363c; overflow: hidden; }.trace-head { display: flex; justify-content: space-between; gap: 20px; padding: 19px 22px; border-bottom: 1px solid #37393f; }.eyebrow { color: #7ca8e9; letter-spacing: .13em; font-size: 11px; font-weight: 700; }.trace-head h2 { font-size: 17px; line-height: 1.4; margin: 5px 0; overflow-wrap: anywhere; }.trace-head p { margin: 0; color: #a6a9b1; font-size: 12px; }.trace-totals { display: flex; flex-direction: column; gap: 4px; white-space: nowrap; font-size: 12px; color: #a6a9b1; }
.trace-toolbar { display: flex; justify-content: space-between; gap: 10px; padding: 9px 12px; background: #28292d; border-bottom: 1px solid #3c3d43; }.tabs { display: flex; gap: 4px; }.tabs button { border: 0; border-radius: 8px; background: transparent; color: #a7aab2; padding: 8px 12px; cursor: pointer; }.tabs button.active { background: #3a3b41; color: #fff; }.trace-toolbar input { width: min(240px, 35%); padding: 7px 11px; color: #f3f4f6; background: #303136; border: 1px solid #50525a; border-radius: 8px; }
.timeline { padding: 12px 20px; border-bottom: 1px solid #34363c; }.lane { display: flex; align-items: center; height: 23px; gap: 10px; }.lane-label { width: 56px; flex: none; color: #999da7; font-size: 12px; }.lane-track { position: relative; height: 15px; flex: 1; background: repeating-linear-gradient(90deg, transparent 0, transparent calc(25% - 1px), #33363c calc(25% - 1px), #33363c 25%); }.lane-bar { position: absolute; top: 2px; height: 11px; border-radius: 2px; }.lane-bar.model { background: #9373be; }.lane-bar.tool { background: #d38b3c; }.lane-bar.subagent { background: #56a57e; }
.events { list-style: none; padding: 0; margin: 0; max-height: 560px; overflow-y: auto; }.event-row { display: flex; align-items: center; gap: 11px; padding: 11px 17px; border-bottom: 1px solid #303136; font-size: 13px; }.event-row:hover { background: #24262b; }.phase-tag { padding: 4px 7px; border-radius: 5px; white-space: nowrap; font-weight: 600; }.phase-tag.user { background: #2e425f; color: #82aff4; }.phase-tag.model { background: #393146; color: #bb97e6; }.phase-tag.tool { background: #483525; color: #efa54f; }.phase-tag.subagent { background: #29443a; color: #78d0a5; }.event-label { min-width: 0; flex: 1; overflow-wrap: anywhere; }.event-status { color: #a6a9b1; white-space: nowrap; }.event-status.failed { color: #ff8989; }.event-status.running { color: #f2c66d; }.event-duration, .event-time { color: #a6a9b1; font-size: 11px; white-space: nowrap; }
.trace-note, .trace-state { padding: 15px 19px; color: #a6a9b1; font-size: 12px; line-height: 1.6; }.trace-failure { margin: 0; padding: 12px 18px; background: #4a2929; color: #ffb0b0; overflow-wrap: anywhere; }.error { color: #b91c1c; }.trace-state.alert { color: #ff8989; }
@media (max-width: 1000px) { .layout { grid-template-columns: 1fr; }.runs { max-height: 220px; overflow-y: auto; }.trace-totals { display: none; } } @media (max-width: 700px) { .stats { grid-template-columns: repeat(2, 1fr); }.event-time { display: none; }.trace-toolbar { flex-wrap: wrap; }.trace-toolbar input { width: 100%; }.event-row { gap: 6px; padding: 10px; } }
</style>
