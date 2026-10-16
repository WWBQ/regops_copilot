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
  getCodingThread,
  listCodingThreads,
  prepareCodingSandbox,
  streamCodingMessage,
  uploadCodingFile,
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
const activeSandboxReady = ref(false)
const showExportReminder = ref(false)
const workspaceNotice = ref('')
const sandboxActionBusy = ref(false)
const error = ref('')
const listRef = ref<HTMLElement | null>(null)
const activeEvidence = ref<Citation | null>(null)
const inputUnavailableText = computed(() => {
  if (!ready.value) return '正在连接 Agent 服务…'
  if (agentOk.value === false) return isCoding.value ? 'AI Coding 暂不可用' : '金融风险审计助手暂不可用'
  if (!selectedModel.value) return '没有可用模型'
  return isCoding.value ? 'AI Coding 暂不可用' : '金融风险审计助手暂不可用'
})
const codingSandboxHint = computed(() => {
  if (error.value) return error.value
  if (workspaceNotice.value) return workspaceNotice.value
  return currentThreadId.value
    ? '当前会话还没有沙箱；可新建后上传代码。'
    : '沙箱会在需要运行代码时自动创建；也可以先新建，再上传代码。'
})
const showSandboxNotice = computed(() => isCoding.value && (
  !!error.value || !!workspaceNotice.value || !activeSandboxReady.value
))
let abortController: AbortController | null = null
let workspaceNoticeTimer: ReturnType<typeof setTimeout> | null = null
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
    busy: loading.value || sandboxActionBusy.value,
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
  const restored = groupAgentHistory(thread.messages, isCoding.value ? 'coding_agent' : 'risk_agent')
  if (isCoding.value && thread.latestTodos?.length) {
    const lastMessage = restored.at(-1)
    if (lastMessage?.role === 'assistant') {
      lastMessage.todos = thread.latestTodos
    } else if (lastMessage?.role === 'user') {
      restored.push({
        id: `${thread.id}-latest-todos`, role: 'assistant', route: 'coding_agent',
        content: '', todos: thread.latestTodos, streaming: thread.status === 'running',
      })
    }
  }
  return restored
}

async function reloadThreads() {
  threads.value = await (isCoding.value ? listCodingThreads() : listRiskAgentThreads())
  agentOk.value = true
  syncBridge()
}

async function reloadModels() {
  const options = await (isCoding.value ? getCodingOptions() : getRiskAgentOptions())
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
  if (loading.value || sandboxActionBusy.value) return
  error.value = ''
  try {
    const thread = await (isCoding.value ? getCodingThread(id) : getRiskAgentThread(id))
    activeEvidence.value = null
    currentThreadId.value = thread.id
    workspaceNotice.value = ''
    activeSandboxReady.value = !!thread.sandboxReady
    showExportReminder.value = isCoding.value && thread.snapshotReady === true
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
  if (loading.value || sandboxActionBusy.value) return
  currentThreadId.value = null
  workspaceNotice.value = ''
  activeSandboxReady.value = false
  showExportReminder.value = false
  messages.value = []
  activeEvidence.value = null
  activeReplyId = null
  activeUserId = null
  runParts = []
  error.value = ''
  syncBridge()
}

async function deleteThread(id: string) {
  if (loading.value || sandboxActionBusy.value) return
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
    const reply = activeReply()
    if (isCoding.value && reply && Array.isArray(data.todos)) {
      const todos = data.todos.filter((item): item is { content: string; status: 'pending' | 'in_progress' | 'completed' } => {
        if (!item || typeof item !== 'object') return false
        const todo = item as { content?: unknown; status?: unknown }
        return typeof todo.content === 'string'
          && ['pending', 'in_progress', 'completed'].includes(String(todo.status))
      })
      if (todos.length) {
        reply.todos = todos
        const active = todos.find((item) => item.status === 'in_progress')
        if (active) reply.statusText = active.content
      }
    }
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
    if (isCoding.value) {
      activeSandboxReady.value = data.sandboxReady === true
      showExportReminder.value = data.snapshotReady === true
    }
    const reply = activeReply()
    if (reply && !reply.content) updateReply('')
    if (reply) reply.statusText = ''
  }
  if (event === 'export_warning' && isCoding.value) {
    error.value = String(data.message ?? '导出快照保存失败，请手动导出')
  }
  if (event === 'workspace_notice' && isCoding.value) {
    workspaceNotice.value = String(data.message ?? '已创建新的空沙箱工作区')
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
    error.value = cause instanceof ApiRequestError
      ? `导出失败：${cause.message}`
      : formatUserFacingError(cause)
  }
}

async function prepareSandbox() {
  if (!isCoding.value || loading.value || sandboxActionBusy.value) return
  sandboxActionBusy.value = true
  error.value = ''
  workspaceNotice.value = ''
  syncBridge()
  try {
    const result = await prepareCodingSandbox(currentThreadId.value)
    agentOk.value = true
    currentThreadId.value = result.thread.id
    activeSandboxReady.value = result.thread.sandboxReady === true
    workspaceNotice.value = result.workspace_notice
      || (result.sandbox_created ? '沙箱已创建，可以上传或编写代码。' : '沙箱已连接，可以继续使用。')
    await reloadThreads()
  } catch (cause) {
    error.value = formatUserFacingError(cause)
  } finally {
    sandboxActionBusy.value = false
    syncBridge()
  }
}

async function onCodeFilesSelected(files: File[]) {
  if (!files.length || loading.value || sandboxActionBusy.value) return
  sandboxActionBusy.value = true
  error.value = ''
  workspaceNotice.value = ''
  syncBridge()
  let uploaded = 0
  try {
    for (const file of files) {
      if (!file.size || file.size > 20 * 1024 * 1024) throw new Error(`${file.name} 不能为空或超过 20 MiB`)
    }
    let threadId = currentThreadId.value
    if (!threadId) {
      const prepared = await prepareCodingSandbox(null)
      agentOk.value = true
      threadId = prepared.thread.id
      currentThreadId.value = threadId
      activeSandboxReady.value = prepared.thread.sandboxReady === true
    }
    for (const file of files) {
      const result = await uploadCodingFile(threadId, file)
      agentOk.value = true
      uploaded += result.file_count
      activeSandboxReady.value = result.thread.sandboxReady === true
      if (result.workspace_notice) workspaceNotice.value = result.workspace_notice
      if (!result.snapshot_saved) throw new Error(result.message)
    }
    workspaceNotice.value = `${workspaceNotice.value ? `${workspaceNotice.value} ` : ''}已导入 ${uploaded} 个文件，代码快照已保存。`
    showExportReminder.value = true
    await reloadThreads()
  } catch (cause) {
    error.value = `${uploaded ? `已导入 ${uploaded} 个文件；` : ''}${formatUserFacingError(cause)}`
    try { await reloadThreads() } catch { /* Keep the original upload error visible. */ }
  } finally {
    sandboxActionBusy.value = false
    syncBridge()
  }
}

async function send(text: string) {
  const content = text.trim()
  if (!content || loading.value || sandboxActionBusy.value || !selectedModel.value) return
  const requestContent = content
  showExportReminder.value = false
  error.value = ''
  const localId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  activeUserId = `local-user-${localId}`
  activeReplyId = `risk-reply-${localId}`
  runParts = []
  messages.value.push({ id: activeUserId, role: 'user', content: requestContent })
  messages.value.push({
    id: activeReplyId, role: 'assistant', content: '', route: isCoding.value ? 'coding_agent' : 'risk_agent',
    streaming: true, statusText: isCoding.value ? '正在处理 AI Coding 请求…' : '正在启动金融风险初筛…', stages: [],
  })
  loading.value = true
  syncBridge()
  abortController = new AbortController()
  try {
    await (isCoding.value ? streamCodingMessage : streamRiskAgentMessage)(
      currentThreadId.value, requestContent, selectedModel.value, applyEvent, abortController.signal,
    )
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      error.value = '已停止接收；后台任务可能仍在运行，请稍后刷新会话。'
    } else {
      if (cause instanceof ApiRequestError && [502, 503, 504].includes(cause.status)) agentOk.value = false
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
watch(workspaceNotice, (notice) => {
  if (workspaceNoticeTimer) clearTimeout(workspaceNoticeTimer)
  workspaceNoticeTimer = notice ? setTimeout(() => { workspaceNotice.value = '' }, 6000) : null
})
onMounted(async () => {
  try {
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
  if (workspaceNoticeTimer) clearTimeout(workspaceNoticeTimer)
  if (bridge) bridge.value = createEmptyChatBridge()
})
</script>

<template>
  <section class="risk-agent-workspace" :class="{ 'with-evidence': activeEvidence }">
    <section class="chat-panel risk-agent-panel">
      <header class="chat-header">
        <div>
          <h1>{{ isCoding ? 'AI Coding' : '金融风险审计助手' }}</h1>
          <p v-if="isCoding">使用 DeepAgents 在独立沙箱中分析、实现和审查代码。开发任务先给出方案，确认后再实施；完成后请导出代码。</p>
          <p v-else>对公开财报做风险线索初筛，结合财务事实与年报证据提出待核查问题；不出具审计或投资结论。</p>
        </div>
      </header>

      <div ref="listRef" class="message-list">
        <div v-if="!messages.length" class="risk-welcome">
          <h2>{{ isCoding ? '从一个代码任务开始' : '从一个核查目标开始' }}</h2>
          <p>{{ isCoding ? '例如：在沙箱 /projects 中创建一个 Python 小项目，先给出实施方案。' : '例如：检查美的集团近三年财务数据中值得人工复核的风险信号，并列明证据缺口。' }}</p>
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
        <div v-if="showSandboxNotice" class="coding-sandbox-notice" :class="{ 'is-error': !!error }" :role="error ? 'alert' : 'status'">
          <span>{{ codingSandboxHint }}</span>
          <div class="coding-sandbox-controls">
            <button v-if="agentOk === false" type="button" :disabled="loading || sandboxActionBusy" @click="retryConnection">重试连接</button>
            <button type="button" :disabled="loading || sandboxActionBusy" @click="prepareSandbox">
              {{ sandboxActionBusy ? '正在处理…' : currentThreadId ? '重连/新建沙箱' : '新建沙箱' }}
            </button>
          </div>
        </div>
        <div v-if="isCoding && showExportReminder" class="export-reminder" role="status">
          <span>如需在本地保留代码，可下载 ZIP；下载需要已保存的快照或仍可用的沙箱。</span>
          <button class="export-reminder-button" type="button" :disabled="loading" @click="exportSandbox">导出代码 ZIP</button>
        </div>
        <div v-if="error && !isCoding" class="risk-error" role="alert">
          {{ error }}
          <button v-if="agentOk === false" type="button" @click="retryConnection">重试连接</button>
        </div>
        <div v-if="!messages.length" class="example-chips">
          <button type="button" class="example-chip" @click="send(isCoding ? '在沙箱中创建一个 Python 示例项目，先给出方案，暂不修改代码' : '对美的集团2024年财报做风险线索初筛，列出需要人工核查的问题和证据缺口')">
            {{ isCoding ? '创建 Python 项目' : '美的 2024 风险初筛' }}
          </button>
        </div>
        <ChatInput
          :loading="loading"
          :disabled="!ready || !selectedModel || sandboxActionBusy"
          :java-ok="true"
          :python-ok="agentOk"
          :allow-attachment="isCoding"
          :attachment-kind="isCoding ? 'code' : 'pdf'"
          :uploading="sandboxActionBusy"
          :models="availableModels"
          :model="selectedModel"
          @update:model="selectModel"
          :placeholder-text="isCoding ? '描述代码任务，Enter 发送' : '输入公司、年份和核查目标，Enter 发送'"
          stop-label="停止接收"
          :unavailable-text="inputUnavailableText"
          @send="send"
          @stop="stopReceiving"
          @attach-files="onCodeFilesSelected"
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
.coding-sandbox-notice { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; padding: 10px 14px; border: 1px solid #ccece5; border-radius: 12px; background: #f2faf8; color: #14574c; font-size: 13px; line-height: 1.5; }
.coding-sandbox-notice.is-error { border-color: #fecaca; background: #fef2f2; color: #991b1b; }
.coding-sandbox-controls { display: flex; flex: none; gap: 8px; }
.coding-sandbox-controls button { border: 1px solid currentColor; border-radius: 8px; background: #fff; color: inherit; padding: 7px 12px; font: inherit; font-size: 12px; font-weight: 600; white-space: nowrap; cursor: pointer; }
.coding-sandbox-controls button:hover:not(:disabled) { background: #ecfdf5; }
.coding-sandbox-notice.is-error .coding-sandbox-controls button:hover:not(:disabled) { background: #fff1f2; }
.coding-sandbox-controls button:disabled { opacity: .55; cursor: not-allowed; }
.export-reminder { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; padding: 10px 14px; border: 1px solid #ccece5; border-radius: 12px; background: #f2faf8; color: #14574c; font-size: 13px; line-height: 1.5; }
.export-reminder-button { flex: none; border: 1px solid var(--accent); border-radius: 8px; background: var(--accent); color: #fff; padding: 7px 12px; font: inherit; font-size: 12px; font-weight: 600; line-height: 1.3; white-space: nowrap; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
.export-reminder-button:hover:not(:disabled) { border-color: var(--accent-hover); background: var(--accent-hover); }
.export-reminder-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.export-reminder-button:disabled { opacity: .55; cursor: not-allowed; }

@media (max-width: 800px) {
  .coding-sandbox-notice { flex-wrap: wrap; }
  .export-reminder { flex-wrap: wrap; }
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
