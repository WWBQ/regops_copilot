<script setup lang="ts">
import { computed, inject, nextTick, ref, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { CHAT_BRIDGE_KEY, type ChatBridge, type ChatSessionMeta } from '../../composables/chatBridge'
import { pageMenuForPath } from '../../config/pageMenu'

const route = useRoute()
const router = useRouter()
const chatBridge = inject(CHAT_BRIDGE_KEY, null) as Ref<ChatBridge> | null

const isChatPage = computed(() => route.path === '/' || route.path.startsWith('/rag'))
const pageItems = computed(() => pageMenuForPath(route.path))

const renamingId = ref<string | null>(null)
const renameDraft = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  if (sameDay) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

async function onItemClick(item: (typeof pageItems.value)[number]) {
  if (item.action === 'new-chat') {
    await chatBridge?.value.newChat()
    return
  }
  if (item.path) {
    router.push(item.path)
  }
}

async function onSwitchSession(sessionId: string) {
  if (renamingId.value) {
    return
  }
  await chatBridge?.value.switchSession(sessionId)
}

async function startRename(session: ChatSessionMeta, event: Event) {
  event.stopPropagation()
  renamingId.value = session.sessionId
  renameDraft.value = session.title
  await nextTick()
  renameInputRef.value?.focus()
  renameInputRef.value?.select()
}

function cancelRename() {
  renamingId.value = null
  renameDraft.value = ''
}

async function commitRename(sessionId: string) {
  const draft = renameDraft.value.trim()
  cancelRename()
  if (!draft) {
    return
  }
  await chatBridge?.value.renameSession(sessionId, draft)
}

async function onDelete(sessionId: string, event: Event) {
  event.stopPropagation()
  if (!window.confirm('确定删除该对话？删除后无法恢复。')) {
    return
  }
  await chatBridge?.value.deleteSession(sessionId)
}
</script>

<template>
  <aside class="page-sidebar">
    <p class="sidebar-label">页面</p>

    <div class="page-actions">
      <button
        v-for="item in pageItems"
        :key="item.id"
        type="button"
        class="page-action primary"
        :disabled="item.action === 'new-chat' && chatBridge?.busy"
        @click="onItemClick(item)"
      >
        <span v-if="item.icon === 'plus'" class="icon" aria-hidden="true">+</span>
        <span v-else-if="item.icon === 'list'" class="icon" aria-hidden="true">☰</span>
        {{ item.label }}
      </button>
    </div>

    <section v-if="isChatPage && chatBridge?.ready" class="chat-history">
      <p class="sidebar-label">对话记录</p>
      <p v-if="!chatBridge?.sessions.length" class="empty-hint">暂无历史对话</p>
      <div
        v-for="session in chatBridge?.sessions ?? []"
        :key="session.sessionId"
        class="history-item"
        :class="{ active: session.sessionId === chatBridge?.activeSessionId }"
        @click="onSwitchSession(session.sessionId)"
      >
        <div class="history-main">
          <input
            v-if="renamingId === session.sessionId"
            ref="renameInputRef"
            v-model="renameDraft"
            class="rename-input"
            type="text"
            maxlength="48"
            @click.stop
            @keydown.enter.prevent="commitRename(session.sessionId)"
            @keydown.esc.prevent="cancelRename"
            @blur="commitRename(session.sessionId)"
          />
          <span v-else class="history-title" :title="session.title">{{ session.title }}</span>
          <span class="history-time">{{ formatTime(session.updatedAt) }}</span>
        </div>
        <div class="history-actions">
          <button
            type="button"
            class="action-btn"
            title="重命名"
            :disabled="chatBridge?.busy"
            @click="startRename(session, $event)"
          >
            ✎
          </button>
          <button
            type="button"
            class="action-btn danger"
            title="删除"
            :disabled="chatBridge?.busy"
            @click="onDelete(session.sessionId, $event)"
          >
            ×
          </button>
        </div>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.page-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: #f8fafc;
  border-right: 1px solid var(--border);
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

.sidebar-label {
  margin: 0 0 8px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #94a3b8;
}

.page-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.page-action {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-strong);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.page-action.primary:hover:not(:disabled) {
  background: #ecfeff;
  border-color: #99f6e4;
}

.page-action:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.page-action .icon {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: #ecfeff;
  color: #0f766e;
  display: grid;
  place-items: center;
  font-size: 14px;
  line-height: 1;
}

.chat-history {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
  padding-right: 2px;
}

.chat-history:hover {
  scrollbar-color: rgba(148, 163, 184, 0.4) transparent;
}

.chat-history::-webkit-scrollbar {
  width: 4px;
}

.chat-history::-webkit-scrollbar-track {
  background: transparent;
  margin: 8px 0;
}

.chat-history::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 999px;
}

.chat-history:hover::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.4);
}

.empty-hint {
  margin: 0;
  padding: 8px;
  font-size: 12px;
  color: var(--muted);
}

.history-item {
  width: 100%;
  border: none;
  background: transparent;
  border-radius: 10px;
  padding: 8px;
  cursor: pointer;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 4px;
}

.history-item:hover {
  background: #eef2f7;
}

.history-item.active {
  background: #e0f2fe;
}

.history-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-title {
  font-size: 13px;
  color: var(--text-strong);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rename-input {
  width: 100%;
  border: 1px solid #99f6e4;
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 13px;
  color: var(--text-strong);
  background: #ffffff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(45, 212, 191, 0.15);
}

.history-time {
  font-size: 11px;
  color: #94a3b8;
}

.history-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.history-item:hover .history-actions,
.history-item.active .history-actions {
  opacity: 1;
}

.action-btn {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  display: grid;
  place-items: center;
}

.action-btn:hover:not(:disabled) {
  background: #e2e8f0;
  color: var(--text-strong);
}

.action-btn.danger:hover:not(:disabled) {
  background: #fee2e2;
  color: #b91c1c;
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .page-sidebar {
    width: 200px;
    padding: 12px 8px;
  }

  .history-actions {
    opacity: 1;
  }
}
</style>
