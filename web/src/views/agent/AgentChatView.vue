<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { CHAT_BRIDGE_KEY, createEmptyChatBridge } from '../../composables/chatBridge'
import { ApiRequestError, formatUserFacingError } from '../../api/client'
import {
  deleteRiskAgentThread,
  getRiskAgentHealth,
  getRiskAgentOptions,
  getRiskAgentThread,
  listRiskAgentThreads,
  streamRiskAgentMessage,
  type RiskAgentEvent,
  type RiskAgentThread,
} from '../../api/riskAgent'
import {
  deleteCodingThread,
  downloadCodingSnapshot,
  getCodingHealth,
  getCodingOptions,
  getCodingProjects,
  getCodingThread,
  listCodingThreads,
  streamCodingMessage,
} from '../../api/codingAgent'
import type { ChatMessage as ChatMessageType, Citation, RiskAuditResult } from '../../types/chat'
import ChatInput from '../../components/chat/ChatInput.vue'
import ChatMessage from '../../components/chat/ChatMessage.vue'
import RiskEvidencePanel from './RiskEvidencePanel.vue'
import {
  groupAgentHistory,
  presentAgentRun,
  updateAgentTextPart,
  type AgentTextPart,
} from './riskAgentPresentation'

const props = defineProps<{ mode: 'risk' | 'coding' }>()
const isCoding = computed(() => props.mode === 'coding')
const bridge = inject(CHAT_BRIDGE_KEY, null)
const threads = ref<RiskAgentThread[]>([])
const currentThreadId = ref<string | null>(null)
const messages = ref<ChatMessageType[]>([])
const loading = ref(false)
const ready = ref(false)
const agentOk = ref<boolean | null>(null)
const availableModels = ref<string[]>([])
const selectedModel = ref('')
const projects = ref<string[]>([])
const selectedProject = ref('')
const sandboxMode = ref(false)
const activeSandboxProject = ref('')
const activeSandboxReady = ref(false)
const error = ref('')
const listRef = ref<HTMLElement | null>(null)
const activeEvidence = ref<Citation | null>(null)
const projectRequired = computed(() => isCoding.value && sandboxMode.value && !selectedProject.value)
const inputUnavailableText = computed(() => {
  if (!ready.value) return '正在连接 Agent 服务…'
  if (agentOk.value === false) return isCoding.value ? 'AI Coding 暂不可用' : '金融风险审计助手暂不可用'
  if (!selectedModel.value) return '没有可用模型'
  if (projectRequired.value) return '请先选择上方的工作项目'
  return isCoding.value ? 'AI Coding 暂不可用' : '金融风险审计助手暂不可用'
})
let abortController: AbortController | null = null
let disposed = false
let runParts: AgentTextPart[] = []
let activeReplyId: string | null = null
let activeUserId: string | null = null

function activeReply(): ChatMessageType | undefined {
  return messages.value.find((message) => message.id === activeReplyId)
}

function updateReply(finalAnswer?: string, citations?: Citation[], riskResult?: RiskAuditResult | null) {
  const reply = activeReply()
  if (!reply) return
  const display = presentAgentRun(runParts, finalAnswer)
  reply.content = display.content
  reply.stages = display.stages
  reply.stageText = display.stageText
  if (finalAnswer !== undefined) {
    reply.statusText = ''
    reply.citations = citations ?? []
    reply.ragUsed = reply.citations.some((citation) => citation.kind === 'document')
    reply.riskResult = riskResult ?? null
  }
}

function eventRiskResult(value: unknown): RiskAuditResult | null {
  if (!value || typeof value !== 'object') return null
  const result = value as Partial<RiskAuditResult>
  if (
    typeof result.company_code !== 'string'
    || typeof result.company_name !== 'string'
    || typeof result.year !== 'number'
    || !Array.isArray(result.findings)
    || !Array.isArray(result.evidence_gaps)
  ) return null
  return result as RiskAuditResult
}

function eventCitations(value: unknown): Citation[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is Citation => {
    if (!item || typeof item !== 'object') return false
    const citation = item as Partial<Citation>
    return typeof citation.doc_id === 'string'
      && typeof citation.page === 'number'
      && typeof citation.snippet === 'string'
  })
}

function syncBridge() {
  if (!bridge || disposed) return
  bridge.value = {
    ready: ready.value,
    busy: loading.value,
    canRename: false,
    activeSessionId: currentThreadId.value ?? '',
    sessions: threads.value.map((thread) => ({
      sessionId: thread.id,
      title: thread.title || (isCoding.value ? 'AI Coding 任务' : '金融风险初筛'),
      updatedAt: new Date(thread.updatedAt).toISOString(),
    })),
    newChat,
    switchSession: selectThread,
    deleteSession: deleteThread,
    renameSession: () => {},
  }
}

function restoreMessages(thread: RiskAgentThread): ChatMessageType[] {
  return groupAgentHistory(thread.messages, isCoding.value ? 'coding_agent' : 'risk_agent')
}

async function reloadThreads() {
  threads.value = await (isCoding.value ? listCodingThreads() : listRiskAgentThreads())
  agentOk.value = true
  syncBridge()
}

async function reloadModels() {
  const options = await (isCoding.value ? getCodingOptions() : getRiskAgentOptions())
  sandboxMode.value = isCoding.value && 'execution_backend' in options && options.execution_backend === 'opensandbox'
  availableModels.value = options.models.map((item) => item.id)
  let stored = ''
  try { stored = localStorage.getItem(isCoding.value ? 'regops_coding_agent_model' : 'regops_risk_agent_model') ?? '' } catch { /* private mode */ }
  selectedModel.value = [selectedModel.value, stored, options.default_agent_model]
    .find((item) => item && availableModels.value.includes(item)) ?? availableModels.value[0] ?? ''
}

function selectModel(model: string) {
  if (!availableModels.value.includes(model)) return
  selectedModel.value = model
  try { localStorage.setItem(isCoding.value ? 'regops_coding_agent_model' : 'regops_risk_agent_model', model) } catch { /* private mode */ }
}

async function retryConnection() {
  error.value = ''
  try {
    const health = await (isCoding.value ? getCodingHealth() : getRiskAgentHealth())
    if (!health.ok) throw new Error('Agent 后端未就绪')
    await reloadModels()
    await reloadThreads()
  } catch (cause) {
    agentOk.value = false
    error.value = formatUserFacingError(cause)
  }
}

async function selectThread(id: string) {
  if (loading.value) return
  error.value = ''
  try {
    const thread = await (isCoding.value ? getCodingThread(id) : getRiskAgentThread(id))
    activeEvidence.value = null
    currentThreadId.value = thread.id
    activeSandboxProject.value = thread.sandboxProject ?? ''
    activeSandboxReady.value = !!thread.sandboxReady
    if (activeSandboxProject.value) selectedProject.value = activeSandboxProject.value
    messages.value = restoreMessages(thread)
    activeReplyId = null
    activeUserId = null
    runParts = []
    syncBridge()
    await scrollToBottom()
  } catch (cause) {
    error.value = formatUserFacingError(cause)
  }
}

function newChat() {
  if (loading.value) return
  currentThreadId.value = null
  activeSandboxProject.value = ''
  activeSandboxReady.value = false
  messages.value = []
  activeEvidence.value = null
  activeReplyId = null
  activeUserId = null
  runParts = []
  error.value = ''
  syncBridge()
}

async function deleteThread(id: string) {
  if (loading.value) return
  try {
    await (isCoding.value ? deleteCodingThread(id) : deleteRiskAgentThread(id))
    if (currentThreadId.value === id) newChat()
    await reloadThreads()
  } catch (cause) {
    error.value = formatUserFacingError(cause)
  }
}

function applyEvent({ event, data }: RiskAgentEvent) {
  const threadId = typeof data.thread_id === 'string' ? data.thread_id : null
  if (event === 'thread_snapshot' && typeof data.id === 'string') {
    currentThreadId.value = data.id
    activeSandboxProject.value = typeof data.sandboxProject === 'string' ? data.sandboxProject : ''
    activeSandboxReady.value = data.sandboxReady === true
    syncBridge()
    return
  }
  if (threadId && currentThreadId.value && threadId !== currentThreadId.value) return
  if (event === 'user_message') {
    const local = messages.value.find((message) => message.id === activeUserId)
    if (local && typeof data.message_id === 'string') local.id = data.message_id
    return
  }
  if (event === 'todo_delta') {
    const todos = Array.isArray(data.todos) ? data.todos : []
    const active = todos.find((item) => item && typeof item === 'object' && item.status === 'in_progress') as { content?: string } | undefined
    const reply = activeReply()
    if (active?.content && reply) reply.statusText = active.content
    return
  }
  if (event === 'text_delta') {
    const id = String(data.message_id ?? '')
    const text = String(data.content ?? '')
    if (id.includes('assistant-startup')) {
      const reply = activeReply()
      if (reply) reply.statusText = text.trim()
      return
    }
    if (!text || !id) return
    runParts = updateAgentTextPart(runParts, id, text, String(data.mode ?? 'append'))
    updateReply()
    return
  }
  if (event === 'final_answer') {
    updateReply(
      String(data.content ?? ''),
      eventCitations(data.citations),
      eventRiskResult(data.risk_result),
    )
    return
  }
  if (event === 'thread_done') {
    if (isCoding.value) activeSandboxReady.value = data.sandboxReady === true
    const reply = activeReply()
    if (reply && !reply.content) updateReply('')
    if (reply) reply.statusText = ''
  }
}

async function exportSandbox() {
  if (!currentThreadId.value || !activeSandboxReady.value || loading.value) return
  error.value = ''
  try {
    const blob = await downloadCodingSnapshot(currentThreadId.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'ai-coding-sandbox.zip'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (cause) {
    error.value = formatUserFacingError(cause)
  }
}

async function send(text: string) {
  const content = text.trim()
  if (!content || loading.value || !selectedModel.value) return
  if (projectRequired.value) {
    error.value = '请先选择工作项目。'
    return
  }
  const requestContent = isCoding.value && selectedProject.value
    ? `目标项目：/projects/${selectedProject.value}\n用户任务：${content}`
    : content
  error.value = ''
  const localId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  activeUserId = `local-user-${localId}`
  activeReplyId = `risk-reply-${localId}`
  runParts = []
  messages.value.push({ id: activeUserId, role: 'user', content: requestContent })
  messages.value.push({
    id: activeReplyId, role: 'assistant', content: '', route: isCoding.value ? 'coding_agent' : 'risk_agent',
    streaming: true, statusText: isCoding.value ? '正在准备 AI Coding 工作区…' : '正在启动金融风险初筛…', stages: [],
  })
  loading.value = true
  syncBridge()
  abortController = new AbortController()
  try {
    await (isCoding.value ? streamCodingMessage : streamRiskAgentMessage)(
      currentThreadId.value, requestContent, selectedModel.value, applyEvent, abortController.signal,
    )
  } catch (cause) {
    if (cause instanceof ApiRequestError && [502, 503, 504].includes(cause.status)) agentOk.value = false
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      error.value = '已停止接收；后台任务可能仍在运行，请稍后刷新会话。'
    } else {
      error.value = formatUserFacingError(cause)
    }
    const reply = activeReply()
    if (reply && !reply.content) {
      if (reply.stageText) reply.stages = [...(reply.stages ?? []), reply.stageText]
      reply.content = isCoding.value ? '本次任务未完成，请查看错误提示。' : '本次初筛未完成，请查看错误提示。'
    }
  } finally {
    abortController = null
    loading.value = false
    messages.value.forEach((message) => { message.streaming = false })
    const reply = activeReply()
    if (reply) {
      reply.stageText = ''
      reply.statusText = ''
    }
    activeReplyId = null
    activeUserId = null
    runParts = []
    try {
      await reloadThreads()
    } catch (cause) {
      agentOk.value = false
      if (!error.value) error.value = formatUserFacingError(cause)
    }
    syncBridge()
  }
}

function stopReceiving() {
  abortController?.abort()
}

async function scrollToBottom() {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

watch(messages, () => { void scrollToBottom() }, { deep: true })
watch(selectedProject, () => {
  if (error.value === '请先选择工作项目。') error.value = ''
})

onMounted(async () => {
  try {
    if (isCoding.value) {
      projects.value = (await getCodingProjects()).projects
      if (projects.value.length === 1) selectedProject.value = projects.value[0]
    }
    await reloadModels()
    await reloadThreads()
    if (threads.value.length) await selectThread(threads.value[0].id)
  } catch (cause) {
    agentOk.value = false
    error.value = formatUserFacingError(cause)
  } finally {
    ready.value = true
    syncBridge()
  }
})

onBeforeUnmount(() => {
  disposed = true
  abortController?.abort()
  if (bridge) bridge.value = createEmptyChatBridge()
})
</script>

<template>
  <section class="risk-agent-workspace" :class="{ 'with-evidence': activeEvidence }">
    <section class="chat-panel risk-agent-panel">
      <header class="chat-header">
        <div>
          <h1>{{ isCoding ? 'AI Coding' : '金融风险审计助手' }}</h1>
          <p v-if="isCoding">使用 DeepAgents 分析、实现和审查工作区代码。开发任务会先给出方案，确认后再实施；{{ sandboxMode ? '当前为 OpenSandbox 隔离模式，修改需导出后人工合并。' : '当前为本机工作区模式。' }}</p>
          <p v-else>对公开财报做风险线索初筛，结合财务事实与年报证据提出待核查问题；不出具审计或投资结论。</p>
        </div>
      </header>

      <div v-if="isCoding" class="coding-project-bar">
        <label for="coding-project">工作项目</label>
        <select id="coding-project" v-model="selectedProject" :disabled="loading || (sandboxMode && activeSandboxReady)">
          <option value="">{{ sandboxMode ? '请选择项目' : '整个工作区' }}</option>
          <option v-if="activeSandboxProject && !projects.includes(activeSandboxProject)" :value="activeSandboxProject">{{ activeSandboxProject }}（沙箱快照）</option>
          <option v-for="project in projects" :key="project" :value="project">{{ project }}</option>
        </select>
        <span>{{ sandboxMode ? '首次运行复制所选项目快照；沙箱创建后不能在同一会话切换。' : '仅可操作配置的 /projects 工作区；选择项目会将路径写入任务。' }}</span>
        <button v-if="sandboxMode && activeSandboxReady && activeSandboxProject" type="button" :disabled="loading" @click="exportSandbox">导出沙箱项目 ZIP</button>
      </div>

      <div ref="listRef" class="message-list">
        <div v-if="!messages.length" class="risk-welcome">
          <h2>{{ isCoding ? '从一个代码任务开始' : '从一个核查目标开始' }}</h2>
          <p>{{ isCoding ? '例如：分析选中项目的目录结构和测试入口，先给出实施建议。' : '例如：检查美的集团近三年财务数据中值得人工复核的风险信号，并列明证据缺口。' }}</p>
        </div>
        <ChatMessage
          v-for="message in messages"
          :key="message.id"
          :message="message"
          :citation-display="isCoding ? 'navigate' : 'panel'"
          @open-evidence="activeEvidence = $event"
        />
      </div>

      <div class="chat-composer-dock">
        <div v-if="error" class="risk-error" role="alert">
          {{ error }}
          <button v-if="agentOk === false" type="button" @click="retryConnection">重试连接</button>
        </div>
        <div v-if="!messages.length" class="example-chips">
          <button type="button" class="example-chip" @click="send(isCoding ? '分析项目结构、关键模块和测试入口，暂不修改代码' : '对美的集团2024年财报做风险线索初筛，列出需要人工核查的问题和证据缺口')">
            {{ isCoding ? '分析项目结构' : '美的 2024 风险初筛' }}
          </button>
        </div>
        <ChatInput
          :loading="loading"
          :disabled="!ready || !selectedModel || projectRequired"
          :java-ok="true"
          :python-ok="agentOk"
          :allow-attachment="false"
          :models="availableModels"
          :model="selectedModel"
          @update:model="selectModel"
          :placeholder-text="isCoding ? '描述代码任务，Enter 发送' : '输入公司、年份和核查目标，Enter 发送'"
          stop-label="停止接收"
          :unavailable-text="inputUnavailableText"
          @send="send"
          @stop="stopReceiving"
        />
      </div>
    </section>

    <RiskEvidencePanel
      v-if="activeEvidence && !isCoding"
      :citation="activeEvidence"
      @close="activeEvidence = null"
    />
  </section>
</template>

<style scoped>
.risk-agent-workspace {
  flex: 1;
  width: 100%;
  min-height: 0;
  display: flex;
  gap: 16px;
  margin: 0 auto;
}
.risk-agent-workspace.with-evidence { max-width: none; }
.risk-agent-panel { min-height: 0; }
.with-evidence .risk-agent-panel { flex: 1; min-width: 320px; max-width: none; margin: 0; }
.risk-welcome { margin: auto; text-align: center; color: var(--muted); max-width: 500px; }
.risk-welcome h2 { color: var(--text-strong); font-size: 18px; margin-bottom: 8px; }
.risk-error { margin: 0 0 10px; padding: 10px 14px; border: 1px solid #fecaca; border-radius: 10px; background: #fef2f2; color: #991b1b; }
.coding-project-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 10px 18px; border-bottom: 1px solid var(--border); color: var(--muted); font-size: 13px; }
.coding-project-bar label { font-weight: 600; color: var(--text-strong); }
.coding-project-bar select { border: 1px solid var(--border); border-radius: 8px; padding: 6px 8px; background: white; color: var(--text-strong); }

@media (max-width: 800px) {
  .risk-agent-workspace { position: relative; }
  .risk-agent-workspace.with-evidence .risk-agent-panel { max-width: 960px; }
  .risk-agent-workspace :deep(.risk-evidence-panel) {
    position: absolute;
    z-index: 20;
    inset: 0 0 0 auto;
    width: min(94vw, 680px);
    min-width: 0;
  }
}
</style>
