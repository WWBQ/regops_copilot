<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { documentViewerPage } from '../../api/documents'
import type { ChatMessage, Citation } from '../../types/chat'
import { attachCitationMarks, citationAt, renderAssistantMarkdown } from '../../utils/citations'
import { formatLatency, formatTokenCount } from '../../utils/tokens'

const props = defineProps<{
  message: ChatMessage
}>()

const router = useRouter()

const activeCitation = ref<Citation | null>(null)
const popoverPos = ref({ top: 0, left: 0 })

const displayTokenCount = computed(() => {
  return props.message.tokenCount ?? props.message.totalTokens
})

const displayTotalLatency = computed(() => {
  return props.message.totalLatencyMs ?? props.message.latencyMs
})

const showModelOnlyNotice = computed(() => {
  if (
    props.message.role !== 'assistant'
    || props.message.id === 'welcome'
    || props.message.error
    || props.message.streaming
  ) {
    return false
  }
  if (props.message.ragUsed || (props.message.citations?.length ?? 0) > 0) {
    return false
  }
  return ![
    'metric',
    'metric_blocked',
    'metric_clarify',
    'rag',
    'rag_blocked',
    'rag_compare',
    'rag_compare_blocked',
  ].includes(props.message.route ?? '')
})

const routeLabel = computed(() => {
  const route = props.message.route
  if (typeof props.message.content === 'string' && props.message.content.includes('【数字校验拦截】')) {
    return '数字拦截'
  }
  if (route === 'metric' || route === 'metric_blocked' || route === 'metric_clarify') {
    return '问数'
  }
  if (route === 'rag' || route === 'rag_blocked' || props.message.ragUsed) {
    return route === 'rag_blocked' ? '数字拦截' : 'RAG'
  }
  return ''
})

const showUsage = computed(() => {
  if (props.message.id === 'welcome' || props.message.error) {
    return false
  }
  if (props.message.role === 'user') {
    return displayTokenCount.value != null && displayTokenCount.value > 0
  }
  return displayTokenCount.value != null || displayTotalLatency.value != null
})

const boundCitations = computed(() => {
  if (props.message.role !== 'assistant' || props.message.error) {
    return []
  }
  return attachCitationMarks(props.message.content, props.message.citations ?? []).citations
})

const htmlContent = computed(() => {
  if (props.message.role !== 'assistant' || props.message.error) {
    return null
  }
  return renderAssistantMarkdown(props.message.content, props.message.citations)
})

function closePopover() {
  activeCitation.value = null
}

function openPopover(citation: Citation, target: HTMLElement) {
  const bubble = target.closest('.bubble') as HTMLElement | null
  if (!bubble) {
    return
  }
  const bubbleRect = bubble.getBoundingClientRect()
  const targetRect = target.getBoundingClientRect()
  activeCitation.value = citation
  popoverPos.value = {
    top: targetRect.bottom - bubbleRect.top + 6,
    left: Math.min(
      Math.max(8, targetRect.left - bubbleRect.left),
      bubbleRect.width - 280,
    ),
  }
}

function onContentClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  const button = target?.closest('.cite-mark') as HTMLElement | null
  if (!button || !boundCitations.value.length) {
    return
  }
  event.preventDefault()
  event.stopPropagation()
  const index = Number.parseInt(button.dataset.citeIndex ?? '', 10)
  const citation = citationAt(boundCitations.value, index)
  if (!citation) {
    return
  }
  if (activeCitation.value === citation) {
    closePopover()
    return
  }
  openPopover(citation, button)
}

function citationActionLabel(citation: Citation): string {
  if (citation.kind === 'facts' || citation.href) {
    return '打开事实库'
  }
  return '查看年报页'
}

function openCitation(citation: Citation) {
  if (citation.href) {
    void router.push(citation.href)
  } else if (citation.doc_id) {
    void router.push(documentViewerPage(citation.doc_id, citation.page))
  }
  closePopover()
}
</script>

<template>
  <article class="message" :class="message.role" @click="closePopover">
    <div class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</div>
    <div class="bubble" @click.stop>
      <p v-if="showModelOnlyNotice" class="model-only-notice">模型回答，仅供参考</p>
      <p v-if="routeLabel" class="route-tag" :data-route="message.route || ''">{{ routeLabel }}</p>
      <p v-if="message.attachmentName" class="attachment-tag">📎 {{ message.attachmentName }}</p>
      <p v-if="message.streaming && !message.content" class="typing-status">
        {{ message.statusText || '正在回复…' }}
      </p>
      <div
        v-else-if="htmlContent"
        class="content markdown-body"
        :class="{ streaming: message.streaming }"
        v-html="htmlContent"
        @click="onContentClick"
      />
      <p v-else class="content" :class="{ streaming: message.streaming }">{{ message.content }}</p>

      <div
        v-if="activeCitation"
        class="cite-popover"
        :style="{ top: `${popoverPos.top}px`, left: `${popoverPos.left}px` }"
        @click.stop
      >
        <p class="cite-popover-title">
          {{ activeCitation.title || activeCitation.doc_id }}
          <template v-if="activeCitation.kind !== 'facts' && activeCitation.page">
            · 第 {{ activeCitation.page }} 页
          </template>
        </p>
        <p class="cite-popover-snippet">{{ activeCitation.snippet }}</p>
        <div class="cite-popover-actions">
          <button type="button" class="cite-open-btn" @click="openCitation(activeCitation)">
            {{ citationActionLabel(activeCitation) }}
          </button>
          <button type="button" class="cite-close-btn" @click="closePopover">关闭</button>
        </div>
      </div>

      <p v-if="showUsage" class="usage-stats">
        <template v-if="message.role === 'user'">
          输入 Token {{ formatTokenCount(displayTokenCount ?? 0) }}
        </template>
        <template v-else>
          <template v-if="displayTokenCount != null">
            输出 Token {{ formatTokenCount(displayTokenCount) }}
          </template>
          <template v-if="message.promptTokenCount">
            · 上下文 Token {{ formatTokenCount(message.promptTokenCount) }}
          </template>
          <template v-if="displayTotalLatency != null">
            <template v-if="displayTokenCount != null || message.promptTokenCount"> · </template>
            总耗时 {{ formatLatency(displayTotalLatency) }}
          </template>
        </template>
      </p>

    </div>
  </article>
</template>

<style scoped>
.bubble {
  position: relative;
}

.route-tag {
  display: inline-flex;
  margin: 0 0 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #ecfeff;
  color: #0f766e;
  font-size: 11px;
  font-weight: 700;
}

.route-tag[data-route='metric_blocked'],
.route-tag[data-route='metric_clarify'] {
  background: #fff7ed;
  color: #c2410c;
}

.route-tag[data-route='rag'] {
  background: #eef2ff;
  color: #4338ca;
}

.route-tag[data-route='rag_blocked'] {
  background: #fff7ed;
  color: #c2410c;
}

.model-only-notice {
  display: table;
  margin: 0 0 10px;
  padding: 3px 9px;
  border: 1px solid #fed7aa;
  border-radius: 999px;
  background: #fff7ed;
  color: #c2410c;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.4;
}

.attachment-tag {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted);
}

.usage-stats {
  margin: 10px 0 0;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  font-size: 11px;
  color: #94a3b8;
  text-align: right;
}

.message.user .usage-stats {
  text-align: right;
}

.message.assistant .usage-stats {
  text-align: left;
}

.markdown-body :deep(.cite-mark) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  margin: 0 2px;
  padding: 0 5px;
  border: none;
  border-radius: 999px;
  background: #ecfeff;
  color: #0f766e;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  vertical-align: super;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.markdown-body :deep(.cite-mark:hover) {
  background: #99f6e4;
  color: #115e59;
}

.cite-popover {
  position: absolute;
  z-index: 20;
  width: min(320px, calc(100% - 16px));
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.14);
}

.cite-popover-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  color: #0f766e;
}

.cite-popover-snippet {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
  max-height: 120px;
  overflow: auto;
}

.cite-popover-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.cite-open-btn,
.cite-close-btn {
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.cite-open-btn {
  border: none;
  background: #0d9488;
  color: #ffffff;
}

.cite-open-btn:hover {
  background: #0f766e;
}

.cite-close-btn {
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--muted);
}

.markdown-body :deep(p) {
  margin: 0 0 0.75em;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 0.6em 0 0.4em;
  color: var(--text-strong);
  line-height: 1.35;
}

.markdown-body :deep(h1) {
  font-size: 1.25em;
}

.markdown-body :deep(h2) {
  font-size: 1.12em;
}

.markdown-body :deep(h3) {
  font-size: 1.05em;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.4em 0 0.75em;
  padding-left: 1.4em;
}

.markdown-body :deep(li + li) {
  margin-top: 0.25em;
}

.markdown-body :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.35em 0.8em;
  border-left: 3px solid var(--accent);
  color: var(--muted);
  background: rgba(13, 148, 136, 0.06);
}

.markdown-body :deep(code) {
  font-family: var(--mono);
  font-size: 0.92em;
  background: #eef2f7;
  padding: 0.12em 0.35em;
  border-radius: 4px;
}

.markdown-body :deep(pre) {
  margin: 0.6em 0;
  padding: 12px 14px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 10px;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.markdown-body :deep(a:not(.cite-mark)) {
  color: var(--accent);
  text-decoration: underline;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.6em 0;
  font-size: 0.95em;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f8fafc;
}

.typing-status {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}

.content.streaming::after {
  content: '▍';
  display: inline-block;
  margin-left: 2px;
  color: var(--accent);
  animation: caret 1s step-end infinite;
}

@keyframes caret {
  50% {
    opacity: 0;
  }
}
</style>
