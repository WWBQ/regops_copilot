<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'

import ChatComposer from './ChatComposer.vue'
import ChatMessage from './ChatMessage.vue'
import SessionSidebar from './SessionSidebar.vue'
import { useAgentStore } from '../stores/agent'

const agent = useAgentStore()
const messageList = ref(null)

watch(
  () => agent.messages.map((message) => {
    const length = message.chunks?.map((chunk) => {
      if (chunk.kind === 'todo') return JSON.stringify(chunk.todos || [])
      return chunk.text || ''
    }).join('').length || 0
    return `${message.id}:${length}`
  }).join('|'),
  async () => {
    await nextTick()
    if (messageList.value) {
      messageList.value.scrollTop = messageList.value.scrollHeight
    }
  },
)

onMounted(() => {
  agent.bootstrap()
})
</script>

<template>
  <main class="app-shell">
    <SessionSidebar
      :threads="agent.threads"
      :active-id="agent.currentThreadId"
      :disabled="agent.streaming"
      @new-thread="agent.createThread"
      @select-thread="agent.selectThread"
      @delete-thread="agent.deleteThread"
    />

    <section class="workspace">
      <header
        v-if="agent.currentThread && (agent.currentThread.status || agent.currentThread.branch || agent.currentThread.pr?.url)"
        class="workspace-header"
      >
        <div class="thread-meta">
          <span v-if="agent.currentThread.status">状态：{{ agent.currentThread.status }}</span>
          <span v-if="agent.currentThread.branch">分支：{{ agent.currentThread.branch }}</span>
          <a v-if="agent.currentThread.pr?.url" :href="agent.currentThread.pr.url" target="_blank">PR</a>
        </div>
      </header>

      <div ref="messageList" class="message-list">
        <div v-if="agent.loading" class="empty-state">正在加载会话...</div>

        <ChatMessage
          v-for="message in agent.messages"
          :key="message.id"
          :message="message"
        />

        <div v-if="agent.error" class="error-banner">{{ agent.error }}</div>
      </div>

      <ChatComposer
        :disabled="agent.streaming"
        :model="agent.selectedModel"
        :effort="agent.selectedEffort"
        @send="agent.submit"
        @stop="agent.stopStream"
      />
    </section>
  </main>
</template>
