<script setup lang="ts">
import { inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

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
import type { ChatMessage as ChatMessageType, Citation, RiskAuditResult } from '../../types/chat'
import ChatInput from '../../components/chat/ChatInput.vue'
import ChatMessage from '../../components/chat/ChatMessage.vue'
import {
  groupRiskAgentHistory,
  presentAgentRun,
  updateAgentTextPart,
  type AgentTextPart,
} from './riskAgentPresentation'

const bridge = inject(CHAT_BRIDGE_KEY, null)
const threads = ref<RiskAgentThread[]>([])
const currentThreadId = ref<string | null>(null)
const messages = ref<ChatMessageType[]>([])
const loading = ref(false)
const ready = ref(false)
const agentOk = ref<boolean | null>(null)
const availableModels = ref<string[]>([])
const selectedModel = ref('')
const error = ref('')
const listRef = ref<HTMLElement | null>(null)
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
      title: thread.title || '金融风险初筛',
      updatedAt: new Date(thread.updatedAt).toISOString(),
    })),
    newChat,
    switchSession: selectThread,
    deleteSession: deleteThread,
    renameSession: () => {},
  }
}

function restoreMessages(thread: RiskAgentThread): ChatMessageType[] {
  return groupRiskAgentHistory(thread.messages)
}

async function reloadThreads() {
  threads.value = await listRiskAgentThreads()
  agentOk.value = true
  syncBridge()
}

async function reloadModels() {
  const options = await getRiskAgentOptions()
  availableModels.value = options.models.map((item) => item.id)
  let stored = ''
  try { stored = localStorage.getItem('regops_risk_agent_model') ?? '' } catch { /* private mode */ }
  selectedModel.value = [selectedModel.value, stored, options.default_agent_model]
    .find((item) => item && availableModels.value.includes(item)) ?? availableModels.value[0] ?? ''
}

function selectModel(model: string) {
  if (!availableModels.value.includes(model)) return
  selectedModel.value = model
  try { localStorage.setItem('regops_risk_agent_model', model) } catch { /* private mode */ }
}

async function retryConnection() {
  error.value = ''
  try {
    const health = await getRiskAgentHealth()
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
    const thread = await getRiskAgentThread(id)
    currentThreadId.value = thread.id
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
  messages.value = []
  activeReplyId = null
  activeUserId = null
  runParts = []
  error.value = ''
  syncBridge()
}

async function deleteThread(id: string) {
  if (loading.value) return
  try {
    await deleteRiskAgentThread(id)
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
    const reply = activeReply()
    if (reply && !reply.content) updateReply('')
    if (reply) reply.statusText = ''
  }
}

async function send(text: string) {
  const content = text.trim()
  if (!content || loading.value || !selectedModel.value) return
  error.value = ''
  const localId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  activeUserId = `local-user-${localId}`
  activeReplyId = `risk-reply-${localId}`
  runParts = []
  messages.value.push({ id: activeUserId, role: 'user', content })
  messages.value.push({
    id: activeReplyId, role: 'assistant', content: '', route: 'risk_agent',
    streaming: true, statusText: '正在启动金融风险初筛…', stages: [],
  })
  loading.value = true
  syncBridge()
  abortController = new AbortController()
  try {
    await streamRiskAgentMessage(currentThreadId.value, content, selectedModel.value, applyEvent, abortController.signal)
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
      reply.content = '本次初筛未完成，请查看错误提示。'
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
  if (bridge) bridge.value = createEmptyChatBridge()
})
</script>

<template>
  <section class="chat-panel risk-agent-panel">
    <header class="chat-header">
      <div>
        <h1>金融风险审计助手</h1>
        <p>对公开财报做风险线索初筛，结合财务事实与年报证据提出待核查问题；不出具审计或投资结论。</p>
      </div>
    </header>

    <div ref="listRef" class="message-list">
      <div v-if="!messages.length" class="risk-welcome">
        <h2>从一个核查目标开始</h2>
        <p>例如：检查美的集团近三年财务数据中值得人工复核的风险信号，并列明证据缺口。</p>
      </div>
      <ChatMessage v-for="message in messages" :key="message.id" :message="message" />
    </div>

    <div class="chat-composer-dock">
      <div v-if="error" class="risk-error" role="alert">
        {{ error }}
        <button v-if="agentOk === false" type="button" @click="retryConnection">重试连接</button>
      </div>
      <div v-if="!messages.length" class="example-chips">
        <button type="button" class="example-chip" @click="send('对美的集团2024年财报做风险线索初筛，列出需要人工核查的问题和证据缺口')">
          美的 2024 风险初筛
        </button>
      </div>
      <ChatInput
        :loading="loading"
        :disabled="!ready || !selectedModel"
        :java-ok="true"
        :python-ok="agentOk"
        :allow-attachment="false"
        :models="availableModels"
        :model="selectedModel"
        @update:model="selectModel"
        placeholder-text="输入公司、年份和核查目标，Enter 发送"
        stop-label="停止接收"
        unavailable-text="金融风险审计助手暂不可用"
        @send="send"
        @stop="stopReceiving"
      />
    </div>
  </section>
</template>

<style scoped>
.risk-agent-panel { min-height: 0; }
.risk-welcome { margin: auto; text-align: center; color: var(--muted); max-width: 500px; }
.risk-welcome h2 { color: var(--text-strong); font-size: 18px; margin-bottom: 8px; }
.risk-error { margin: 0 0 10px; padding: 10px 14px; border: 1px solid #fecaca; border-radius: 10px; background: #fef2f2; color: #991b1b; }
</style>
