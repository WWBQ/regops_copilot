<script setup lang="ts">
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { CHAT_BRIDGE_KEY } from '../../composables/chatBridge'
import { SERVICE_HEALTH_KEY } from '../../composables/useServiceHealth'
import { getModels, streamChat } from '../../api/chat'
import { ApiRequestError, formatUserFacingError } from '../../api/client'
import {
  ensureSessionId,
  getStoredSessionId,
  listSessionDocuments,
  startNewSession,
  storeSessionId,
  uploadSessionDocument,
  waitForDocumentReady,
  type SessionDocument,
} from '../../api/sessions'
import {
  createWelcomeMessage,
  clearChatMessages,
  loadChatMessages,
  saveChatMessages,
  loadPendingAsknum,
  savePendingAsknum,
} from '../../utils/chatStorage'
import {
  defaultNewChatTitle,
  deriveSessionTitle,
  listChatSessions,
  rebuildChatSessionsFromStorage,
  removeChatSession,
  renameChatSession,
  upsertChatSession,
} from '../../utils/chatSessions'
import { loadStoredModel, storeModel } from '../../utils/models'
import { estimateTokens, resolveCompletionTokens } from '../../utils/tokens'
import ChatInput from './ChatInput.vue'
import ChatMessage from './ChatMessage.vue'
import type { ChatMessage as ChatMessageType, PendingAsknum } from '../../types/chat'

const props = defineProps<{
  backendOk: boolean | null
  modelName?: string | null
}>()

const emit = defineEmits<{
  connected: [model: string]
  disconnected: []
  refresh: []
}>()

const chatBridge = inject(CHAT_BRIDGE_KEY, null)
const health = inject(SERVICE_HEALTH_KEY, null)
const javaOk = computed(() => health?.javaOk.value ?? props.backendOk)
const pythonOk = computed(() => health?.pythonOk.value ?? props.backendOk)
const pythonDown = computed(() => pythonOk.value === false)

const messages = ref<ChatMessageType[]>([createWelcomeMessage()])
const loading = ref(false)
const uploading = ref(false)
const sessionId = ref<string | null>(null)
const sessionDocs = ref<SessionDocument[]>([])
const listRef = ref<HTMLElement | null>(null)
const abortRef = ref<AbortController | null>(null)
const suppressSessionMeta = ref(false)
const availableModels = ref<string[]>([])
const selectedModel = ref('')
const connectionAlert = ref<string | null>(null)

const pendingRequest = ref<PendingAsknum | null>(null)

const DISCLAIMER = '本回答由 AI 生成，仅供参考，不构成合规或投资建议。'

const pendingHint = computed(() => {
  const hint = pendingRequest.value?.hint?.trim()
  if (hint) {
    return hint
  }
  if (!pendingRequest.value?.missing?.length) {
    return ''
  }
  return '正在补充查询'
})

function rememberPending(session: string | null, pending: PendingAsknum | null | undefined) {
  pendingRequest.value = pending && pending.missing?.length ? pending : null
  if (session) {
    savePendingAsknum(session, pendingRequest.value)
  }
}


function isVisibleStatus(text: string): boolean {
  const t = text.trim()
  if (!t) {
    return false
  }
  if (/^(thought|action|observation|final answer)\s*:/i.test(t)) {
    return false
  }
  if (/思维链|chain of thought/i.test(t)) {
    return false
  }
  return true
}

function connectionBlockedMessage(): string | null {
  if (javaOk.value === false) {
    return 'Java BFF 不可用。登录和审计也会失败，请先恢复 java-service。'
  }
  if (pythonOk.value === false) {
    return '问答服务暂时不可用。审计仍可用。'
  }
  if (javaOk.value === null) {
    return '正在检测服务连接，请稍候再试。'
  }
  return null
}

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function scrollToBottom() {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

function touchSessionMeta(options?: { touchUpdatedAt?: boolean; moveToFront?: boolean }) {
  if (!sessionId.value) {
    return
  }
  const existing = listChatSessions().find((item) => item.sessionId === sessionId.value)
  const touchUpdatedAt = options?.touchUpdatedAt ?? true
  const updatedAt = touchUpdatedAt
    ? new Date().toISOString()
    : (existing?.updatedAt ?? new Date().toISOString())
  const userSent = messages.value.some((item) => item.role === 'user' && item.content.trim())
  const title = existing?.customTitle
    ? existing.title
    : userSent
      ? deriveSessionTitle(messages.value)
      : (existing?.title ?? defaultNewChatTitle(updatedAt))

  upsertChatSession(
    {
      sessionId: sessionId.value,
      title,
      updatedAt,
      customTitle: existing?.customTitle,
    },
    { moveToFront: options?.moveToFront ?? false },
  )
  syncChatBridge()
}

function syncChatBridge() {
  if (!chatBridge) {
    return
  }
  chatBridge.value = {
    ready: true,
    busy: loading.value || uploading.value,
    activeSessionId: sessionId.value ?? '',
    sessions: listChatSessions(),
    newChat: handleNewChat,
    switchSession: handleSwitchSession,
    deleteSession: handleDeleteSession,
    renameSession: handleRenameSession,
  }
}

async function refreshSessionDocs() {
  if (!sessionId.value) {
    return
  }
  try {
    const response = await listSessionDocuments(sessionId.value)
    sessionDocs.value = response.items
  } catch {
    sessionDocs.value = []
  }
}

async function initModels() {
  try {
    const response = await getModels()
    availableModels.value = response.available
    if (availableModels.value.length > 0) {
      const stored = loadStoredModel(availableModels.value[0])
      selectedModel.value = availableModels.value.includes(stored)
        ? stored
        : availableModels.value[0]
    }
  } catch {
    availableModels.value = []
  }
}

function onModelChange(model: string) {
  selectedModel.value = model
  storeModel(model)
}

async function initSession() {
  try {
    rebuildChatSessionsFromStorage()
    sessionId.value = await ensureSessionId()
    pendingRequest.value = loadPendingAsknum(sessionId.value)
    const restored = loadChatMessages(sessionId.value)
    if (restored) {
      messages.value = restored.map((item) => ({ ...item, streaming: false, statusText: undefined }))
    }
    touchSessionMeta({ touchUpdatedAt: false })
    await refreshSessionDocs()
    syncChatBridge()
  } catch (error) {
    if (error instanceof ApiRequestError && (error.status === 502 || error.status === 504)) {
      sessionId.value = getStoredSessionId()
      if (sessionId.value) {
        const restored = loadChatMessages(sessionId.value)
        if (restored) {
          messages.value = restored.map((item) => ({ ...item, streaming: false, statusText: undefined }))
        }
      }
      return
    }
    const detail = formatUserFacingError(error)
    messages.value.push({
      id: uid(),
      role: 'assistant',
      content: `会话初始化失败：${detail}`,
      error: true,
    })
  }
}

async function handleNewChat() {
  if (loading.value || uploading.value) {
    return
  }
  touchSessionMeta({ touchUpdatedAt: true })
  try {
    sessionId.value = await startNewSession()
    rememberPending(sessionId.value, null)
    messages.value = [createWelcomeMessage()]
    sessionDocs.value = []
    touchSessionMeta({ touchUpdatedAt: true, moveToFront: true })
    await scrollToBottom()
    syncChatBridge()
  } catch (error) {
    const detail = error instanceof Error ? error.message : '未知错误'
    messages.value.push({
      id: uid(),
      role: 'assistant',
      content: `无法创建新对话：${detail}`,
      error: true,
    })
    syncChatBridge()
  }
}

async function handleSwitchSession(targetSessionId: string) {
  if (
    !targetSessionId ||
    targetSessionId === sessionId.value ||
    loading.value ||
    uploading.value
  ) {
    return
  }
  storeSessionId(targetSessionId)
  sessionId.value = targetSessionId
  pendingRequest.value = loadPendingAsknum(targetSessionId)
  suppressSessionMeta.value = true
  messages.value = (loadChatMessages(targetSessionId) ?? [createWelcomeMessage()]).map((item) => ({
    ...item,
    streaming: false,
    statusText: undefined,
  }))
  suppressSessionMeta.value = false
  await refreshSessionDocs()
  await scrollToBottom()
  syncChatBridge()
}

async function handleDeleteSession(targetSessionId: string) {
  if (loading.value || uploading.value) {
    return
  }
  removeChatSession(targetSessionId)
  clearChatMessages(targetSessionId)

  if (sessionId.value === targetSessionId) {
    sessionId.value = null
    const remaining = listChatSessions()
    if (remaining.length > 0) {
      await handleSwitchSession(remaining[0].sessionId)
    } else {
      await handleNewChat()
    }
    return
  }
  syncChatBridge()
}

function handleRenameSession(targetSessionId: string, title: string) {
  renameChatSession(targetSessionId, title)
  syncChatBridge()
}

function statusLabel(status: SessionDocument['status']): string {
  switch (status) {
    case 'PENDING':
      return '排队中'
    case 'PROCESSING':
      return '解析中'
    case 'READY':
      return '可用'
    case 'FAILED':
      return '失败'
    default:
      return status
  }
}

async function handleAttach(file: File) {
  const blocked = connectionBlockedMessage()
  if (blocked) {
    connectionAlert.value = blocked
    return
  }
  if (!sessionId.value) {
    await initSession()
  }
  if (!sessionId.value) {
    return
  }

  uploading.value = true
  const userMsgId = uid()
  messages.value.push({
    id: userMsgId,
    role: 'user',
    content: `上传文档：${file.name}`,
    attachmentName: file.name,
    tokenCount: estimateTokens(file.name),
  })
  await scrollToBottom()

  const progressMsgId = uid()
  messages.value.push({
    id: progressMsgId,
    role: 'assistant',
    content: `已收到 **${file.name}**，正在后台解析入库（本会话有效，约 1–5 分钟）…`,
  })
  await scrollToBottom()

  try {
    const upload = await uploadSessionDocument(sessionId.value, file)
    const finalDoc = await waitForDocumentReady(sessionId.value, upload.doc_id, {
      onStatus: (doc) => {
        const index = messages.value.findIndex((item) => item.id === progressMsgId)
        if (index >= 0) {
          messages.value[index] = {
            ...messages.value[index],
            content: `**${file.name}** · 状态：${statusLabel(doc.status)}…`,
          }
        }
      },
    })
    await refreshSessionDocs()

    const index = messages.value.findIndex((item) => item.id === progressMsgId)
    if (index >= 0) {
      if (finalDoc.status === 'READY') {
        messages.value[index] = {
          ...messages.value[index],
          content: `✅ **${file.name}** 已就绪：${finalDoc.page_count ?? '?'} 页 · ${finalDoc.chunk_count ?? '?'} 个片段。现在可以直接提问。`,
        }
      } else {
        messages.value[index] = {
          ...messages.value[index],
          content: `❌ **${file.name}** 解析失败：${finalDoc.error_message ?? '未知错误'}`,
          error: true,
        }
      }
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : '未知错误'
    const index = messages.value.findIndex((item) => item.id === progressMsgId)
    if (index >= 0) {
      messages.value[index] = {
        ...messages.value[index],
        content: `❌ 上传或解析失败：${detail}`,
        error: true,
      }
    }
  } finally {
    uploading.value = false
    await scrollToBottom()
  }
}

async function handleSend(text: string) {
  const blocked = connectionBlockedMessage()
  if (blocked) {
    connectionAlert.value = blocked
    return
  }
  connectionAlert.value = null

  if (!sessionId.value) {
    await initSession()
  }

  messages.value.push({
    id: uid(),
    role: 'user',
    content: text,
    tokenCount: estimateTokens(text),
  })
  await scrollToBottom()

  const assistantId = uid()
  messages.value.push({
    id: assistantId,
    role: 'assistant',
    content: '',
    streaming: true,
    statusText: '正在回复…',
  })
  await scrollToBottom()

  const patchAssistant = (partial: Partial<ChatMessageType>) => {
    const index = messages.value.findIndex((item) => item.id === assistantId)
    if (index < 0) {
      return
    }
    messages.value[index] = { ...messages.value[index], ...partial }
  }

  loading.value = true
  const startedAt = performance.now()
  abortRef.value?.abort()
  const abort = new AbortController()
  abortRef.value = abort
  try {
    const response = await streamChat(
      {
        message: text,
        session_id: sessionId.value ?? undefined,
        use_rag: true,
        model: selectedModel.value || undefined,
      },
      {
        signal: abort.signal,
        onStatus: (statusText) => {
          if (isVisibleStatus(statusText)) {
            patchAssistant({ statusText })
          }
        },
        onMeta: (meta) =>
          patchAssistant({
            ...(meta.route ? { route: meta.route } : {}),
            ...(meta.model ? { model: meta.model } : {}),
          }),
        onDelta: async (chunk) => {
          const current = messages.value.find((item) => item.id === assistantId)
          patchAssistant({
            content: `${current?.content ?? ''}${chunk}`,
            statusText: undefined,
          })
          await nextTick()
        },
      },
    )
    const clientLatencyMs = performance.now() - startedAt
    const tokenCount = resolveCompletionTokens(response)
    const promptTokenCount = response.prompt_tokens ?? 0
    const latencyMs = response.latency_ms && response.latency_ms > 0 ? response.latency_ms : clientLatencyMs
    patchAssistant({
      content: response.reply,
      model: response.model,
      tokenCount: tokenCount > 0 ? tokenCount : undefined,
      promptTokenCount: promptTokenCount > 0 ? promptTokenCount : undefined,
      latencyMs,
      route: response.route,
      streaming: false,
      statusText: undefined,
      ...(response.citations?.length
        ? { citations: response.citations, ragUsed: Boolean(response.rag_used) }
        : {}),
    })
    rememberPending(sessionId.value, response.pending_request)
    emit('connected', response.model)
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError'
    const current = messages.value.find((item) => item.id === assistantId)
    if (aborted) {
      patchAssistant({
        content: current?.content?.trim() ? current.content : '已停止生成。',
        streaming: false,
        statusText: undefined,
      })
    } else {
      patchAssistant({
        content: formatUserFacingError(error),
        error: true,
        streaming: false,
        statusText: undefined,
      })
      if (error instanceof ApiRequestError && (error.status === 502 || error.errorCode === 'upstream_down')) {
        if (health) {
          health.pythonOk.value = false
        }
        void health?.refresh()
      }
    }
  } finally {
    if (abortRef.value === abort) {
      abortRef.value = null
    }
    loading.value = false
    await scrollToBottom()
  }
}

function handleStop() {
  abortRef.value?.abort()
}

onMounted(() => {
  void initModels()
  void initSession()
})

onUnmounted(() => {
  abortRef.value?.abort()
  if (chatBridge) {
    chatBridge.value.ready = false
  }
})

watch(
  messages,
  (value) => {
    if (sessionId.value && !suppressSessionMeta.value) {
      saveChatMessages(sessionId.value, value)
      touchSessionMeta({ touchUpdatedAt: true })
    }
    void scrollToBottom()
  },
  { deep: true },
)

watch([loading, uploading, sessionId], syncChatBridge)

watch(
  [javaOk, pythonOk],
  () => {
    const blocked = connectionBlockedMessage()
    if (javaOk.value === false || pythonOk.value === false) {
      connectionAlert.value = blocked
    } else if (javaOk.value === true) {
      connectionAlert.value = null
    }
  },
)

watch(
  pythonOk,
  (ok) => {
    if (ok === true && availableModels.value.length === 0) {
      void initModels()
    }
  },
)
</script>

<template>
  <section class="chat-panel">
    <header class="chat-header">
      <div>
        <h1>合规问答</h1>
        <p>
          一个助手：已核验的财务数字走问数，叙述问题走年报 RAG；缺少依据时会明确说明。
          📎 可上传仅本会话有效的 PDF。生成中点「停止」取消。引用可点开年报页，不展示思维链。
          <span v-if="sessionId" class="session-tag">会话 {{ sessionId.slice(0, 8) }}…</span>
        </p>
        <p v-if="sessionDocs.length" class="doc-strip">
          本会话文档：
          <span v-for="doc in sessionDocs" :key="doc.doc_id" class="doc-chip" :class="doc.status.toLowerCase()">
            {{ doc.source_filename }}（{{ statusLabel(doc.status) }}）
          </span>
        </p>
      </div>
    </header>

    <div ref="listRef" class="message-list">
      <ChatMessage v-for="item in messages" :key="item.id" :message="item" />
      <p v-if="uploading" class="typing">PDF 解析入库中…</p>
    </div>

    <div class="chat-composer-dock">
      <div v-if="connectionAlert" class="connection-alert" :class="{ warn: pythonDown && javaOk }" role="alert">
        <p>{{ connectionAlert }}</p>
        <p v-if="pythonDown && javaOk" class="alert-links">
          <router-link to="/compliance/audit">审计追踪</router-link>
        </p>
        <button type="button" class="alert-close" aria-label="关闭" @click="connectionAlert = null">×</button>
      </div>

      <div v-if="messages.length <= 1 && !loading" class="example-chips">
        <button type="button" class="example-chip" :disabled="Boolean(connectionBlockedMessage())" @click="handleSend('比亚迪2024年营业收入是多少')">
          问数
        </button>
        <button
          type="button"
          class="example-chip"
          :disabled="Boolean(connectionBlockedMessage())"
          @click="handleSend('对比比亚迪和长城2024年净利润')"
        >
          两家公司问数
        </button>
        <button type="button" class="example-chip" :disabled="Boolean(connectionBlockedMessage())" @click="handleSend('比亚迪2024年年报有哪些风险因素')">
          年报检索
        </button>
        <button type="button" class="example-chip" :disabled="Boolean(connectionBlockedMessage())" @click="handleSend('比亚迪研发投入多不多')">
          研发
        </button>
        <button type="button" class="example-chip" :disabled="Boolean(connectionBlockedMessage())" @click="handleSend('美的2024年营收到底能不能用')">
          待复核
        </button>
      </div>

      <p v-if="pendingHint" class="pending-slot-chip" role="status">{{ pendingHint }}</p>

      <ChatInput
        :model="selectedModel"
        :models="availableModels"
        :loading="loading"
        :uploading="uploading"
        :java-ok="javaOk"
        :python-ok="pythonOk"
        @update:model="onModelChange"
        @send="handleSend"
        @stop="handleStop"
        @attach="handleAttach"
      />

      <footer class="chat-footer">
        <p class="chat-disclaimer">{{ DISCLAIMER }}</p>
      </footer>
    </div>
  </section>
</template>

<style scoped>
.session-tag {
  margin-left: 8px;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
}

.doc-strip {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.doc-chip {
  display: inline-block;
  margin: 4px 6px 0 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  border: 1px solid var(--border);
  font-size: 12px;
}

.doc-chip.ready {
  background: #ecfdf5;
  border-color: #99f6e4;
  color: #115e59;
}

.doc-chip.failed {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

.doc-chip.pending,
.doc-chip.processing {
  background: #fffbeb;
  border-color: #fde68a;
  color: #92400e;
}

.pending-slot-chip {
  margin: 0 0 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1e3a8a;
  font-size: 12px;
  font-weight: 600;
  width: fit-content;
}

.example-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 8px;
}

.example-chip {
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-strong);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.example-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.example-chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.example-chip:disabled:hover {
  border-color: var(--border);
  color: var(--text-strong);
}

.chat-footer {
  padding: 8px 4px 0;
}

.chat-disclaimer {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: #94a3b8;
  text-align: center;
}

.connection-alert {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 13px;
}

.connection-alert.warn {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.connection-alert p {
  margin: 0;
  flex: 1;
  line-height: 1.45;
}

.alert-links {
  flex: 1 1 100%;
  margin: 4px 0 0;
}

.alert-links a {
  color: inherit;
  font-weight: 700;
}

.alert-close {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}
</style>
