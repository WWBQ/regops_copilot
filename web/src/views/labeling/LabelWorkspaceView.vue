<script setup lang="ts">
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { streamChat } from '../../api/chat'
import { ApiRequestError, formatUserFacingError } from '../../api/client'
import { getLabelItem, htmlProxyUrl, pdfUrl, saveLabelItem } from '../../api/labeling'
import ChatInput from '../../components/chat/ChatInput.vue'
import ChatMessage from '../../components/chat/ChatMessage.vue'
import { SERVICE_HEALTH_KEY } from '../../composables/useServiceHealth'
import type { ChatMessage as ChatMessageType } from '../../types/chat'
import type { LabelItem } from '../../types/labeling'

const props = defineProps<{
  backendOk?: boolean | null
}>()

const emit = defineEmits<{
  connected: [model: string]
  disconnected: []
}>()

const health = inject(SERVICE_HEALTH_KEY, null)
const javaOk = computed(() => health?.javaOk.value ?? props.backendOk ?? null)
const pythonOk = computed(() => health?.pythonOk.value ?? props.backendOk ?? null)

const route = useRoute()
const router = useRouter()
const item = ref<LabelItem | null>(null)
const notes = ref('')
const sourceText = ref('')
const status = ref('')
const error = ref('')
const msg = ref('')
const loading = ref(true)
const saving = ref(false)
const chatLoading = ref(false)
const chatAbort = ref<AbortController | null>(null)
const listRef = ref<HTMLElement | null>(null)

const messages = ref<ChatMessageType[]>([
  {
    id: 'welcome',
    role: 'assistant',
    content: '可以把当前条文作为上下文提问。回复来自 python-ai /chat。',
  },
])

const taskId = computed(() => String(route.params.taskId ?? ''))
const idx = computed(() => Number(route.params.idx ?? 0))
const total = computed(() => item.value?.total ?? 0)
const labelOptions = computed(() =>
  item.value?.label_options?.length ? item.value.label_options : ['OK', '有问题', '跳过'],
)

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function loadItem() {
  loading.value = true
  error.value = ''
  msg.value = ''
  try {
    const data = await getLabelItem(taskId.value, idx.value)
    item.value = data
    notes.value = data.notes || ''
    sourceText.value = data.text || data.otext || ''
    status.value = data.status || ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    item.value = null
  } finally {
    loading.value = false
  }
}

async function save(go: '' | 'next' | 'pre') {
  if (!item.value) return
  saving.value = true
  error.value = ''
  try {
    await saveLabelItem(taskId.value, idx.value, {
      id: item.value.detailId,
      text: sourceText.value,
      otext: item.value.otext,
      url: item.value.url,
      type: item.value.type,
      info: item.value.info,
      status: status.value,
      notes: notes.value,
    })
    msg.value = `已保存 ${new Date().toLocaleTimeString()}`
    if (go === 'next') {
      if (idx.value + 1 < total.value) {
        await router.push(`/quality/review/${taskId.value}/${idx.value + 1}`)
      } else {
        msg.value = '已是最后一条'
      }
    }
    if (go === 'pre') {
      if (idx.value - 1 >= 0) {
        await router.push(`/quality/review/${taskId.value}/${idx.value - 1}`)
      } else {
        msg.value = '已是第一条'
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function scrollChat() {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

async function handleSend(text: string) {
  messages.value.push({ id: uid(), role: 'user', content: text })
  await scrollChat()
  const assistantId = uid()
  messages.value.push({
    id: assistantId,
    role: 'assistant',
    content: '',
    streaming: true,
    statusText: '正在回复…',
  })
  await scrollChat()
  chatLoading.value = true
  chatAbort.value?.abort()
  const abort = new AbortController()
  chatAbort.value = abort
  const context = sourceText.value.trim().slice(0, 2500)
  const payload = context
    ? `请协助核对下面的标注文本：\n\n${context}\n\n问题：${text}`
    : text
  try {
    const response = await streamChat(
      { message: payload },
      {
        signal: abort.signal,
        onStatus: (statusText) => {
          const index = messages.value.findIndex((item) => item.id === assistantId)
          if (index >= 0) {
            messages.value[index] = { ...messages.value[index], statusText }
          }
        },
        onDelta: async (chunk) => {
          const index = messages.value.findIndex((item) => item.id === assistantId)
          if (index >= 0) {
            messages.value[index] = {
              ...messages.value[index],
              content: `${messages.value[index].content}${chunk}`,
              statusText: undefined,
            }
          }
          await nextTick()
        },
      },
    )
    const index = messages.value.findIndex((item) => item.id === assistantId)
    if (index >= 0) {
      messages.value[index] = {
        ...messages.value[index],
        content: response.reply,
        model: response.model,
        disclaimer: response.disclaimer,
        streaming: false,
        statusText: undefined,
      }
    }
    emit('connected', response.model)
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    const index = messages.value.findIndex((item) => item.id === assistantId)
    if (index >= 0) {
      if (!aborted) {
        messages.value[index] = {
          ...messages.value[index],
          content: formatUserFacingError(err),
          error: true,
          streaming: false,
          statusText: undefined,
        }
      } else {
        messages.value[index] = {
          ...messages.value[index],
          content: messages.value[index].content.trim() || '已停止生成。',
          error: false,
          streaming: false,
          statusText: undefined,
        }
      }
    }
    if (
      !aborted &&
      !(err instanceof ApiRequestError && (err.status === 502 || err.status === 504))
    ) {
      emit('disconnected')
    } else if (!aborted && health) {
      health.pythonOk.value = false
      void health.refresh()
    }
  } finally {
    if (chatAbort.value === abort) {
      chatAbort.value = null
    }
    chatLoading.value = false
    await scrollChat()
  }
}

function handleStopChat() {
  chatAbort.value?.abort()
}

function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    void save('')
  }
}

watch(() => [taskId.value, idx.value], loadItem)
onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  void loadItem()
})
onUnmounted(() => {
  chatAbort.value?.abort()
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <section class="workspace">
    <aside class="preview">
      <header class="pane-head">
        <strong>预览 {{ idx + 1 }} / {{ total || '—' }}</strong>
        <a v-if="item?.url" :href="item.url" target="_blank" rel="noreferrer" class="url">原文链接</a>
      </header>
      <p v-if="item?.download_msg" class="error">{{ item.download_msg }}</p>
      <iframe
        v-if="item?.type === 'pdf' && item.pdf_filename"
        class="frame"
        :src="pdfUrl(taskId, item.pdf_filename)"
        title="PDF 预览"
      />
      <iframe
        v-else-if="item?.type === 'html'"
        class="frame"
        :src="htmlProxyUrl(taskId, idx)"
        title="HTML 预览"
      />
      <textarea
        v-else-if="item?.type === 'text'"
        class="source"
        :value="item.otext"
        readonly
      />
      <p v-else-if="!loading" class="hint">暂不可预览。</p>
    </aside>

    <div class="editor">
      <header class="pane-head">
        <div>
          <strong>核对与标注</strong>
          <p class="hint">Ctrl/Cmd+S 保存。保存时会写入编辑后的正文。</p>
        </div>
        <button type="button" class="ghost-btn" @click="router.push(`/quality/review/${taskId}`)">返回列表</button>
      </header>

      <p v-if="loading" class="hint">加载中…</p>
      <p v-if="error" class="error">{{ error }}</p>

      <template v-if="item">
        <p class="meta">id：{{ item.detailId || '—' }}</p>
        <label class="field">
          源文本
          <textarea v-model="sourceText" class="source" />
        </label>
        <label class="field">
          备注
          <textarea v-model="notes" class="notes" />
        </label>
        <div class="status-row">
          <label v-for="opt in labelOptions" :key="opt">
            <input v-model="status" type="radio" :value="opt" /> {{ opt }}
          </label>
        </div>
        <div class="actions">
          <button type="button" class="send-btn" :disabled="saving" @click="save('')">保存</button>
          <button type="button" class="ghost-btn" :disabled="saving" @click="save('pre')">上一条</button>
          <button type="button" class="ghost-btn" :disabled="saving" @click="save('next')">下一条</button>
        </div>
        <p v-if="msg" class="ok">{{ msg }}</p>
      </template>

      <section class="mini-chat">
        <h2>问金融 AI</h2>
        <p v-if="pythonOk === false" class="hint">问答暂不可用。本页标注保存仍走 python-ai，AI 挂了保存也会失败；复核和审计不依赖问答。</p>
        <div ref="listRef" class="mini-list">
          <ChatMessage v-for="row in messages" :key="row.id" :message="row" />
        </div>
        <ChatInput
          :loading="chatLoading"
          :disabled="pythonOk === false || javaOk === false"
          :java-ok="javaOk"
          :python-ok="pythonOk"
          :models="[]"
          model=""
          @send="handleSend"
          @stop="handleStopChat"
        />
      </section>
    </div>
  </section>
</template>

<style scoped>
.workspace {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  height: calc(100vh - 48px);
  min-height: 0;
}

.preview,
.editor {
  min-width: 0;
  min-height: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor {
  overflow: auto;
  padding: 0 14px 14px;
}

.pane-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
}

.url {
  color: var(--accent);
  font-size: 13px;
}

.frame {
  flex: 1;
  border: 0;
  width: 100%;
  background: #f8fafc;
}

.source,
.notes {
  width: 100%;
  min-height: 120px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  font: inherit;
  resize: vertical;
}

.field {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 12px;
}

.status-row,
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 8px 0 12px;
}

.meta {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--muted);
}

.ok {
  color: #15803d;
  font-size: 13px;
}

.hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted);
}

.error {
  color: var(--danger);
  padding: 0 14px;
}

.mini-chat {
  margin-top: 8px;
  border-top: 1px dashed var(--border);
  padding-top: 12px;
}

.mini-chat h2 {
  margin: 0 0 8px;
  font-size: 15px;
  color: var(--text-strong);
}

.mini-list {
  max-height: 240px;
  overflow: auto;
  margin-bottom: 10px;
}

@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: 1fr;
    height: auto;
  }

  .frame {
    min-height: 360px;
  }
}
</style>
