<script setup>
import { ref } from 'vue'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  model: {
    type: String,
    default: '',
  },
  effort: {
    type: String,
    default: 'default',
  },
})

const emit = defineEmits(['send', 'stop'])
const draft = ref('')

function send() {
  const content = draft.value.trim()
  if (!content || props.disabled) return
  draft.value = ''
  emit('send', content)
}

function onKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}
</script>

<template>
  <footer class="composer">
    <textarea
      v-model="draft"
      rows="1"
      :disabled="disabled"
      placeholder="继续输入指令"
      @keydown="onKeydown"
    />

    <span class="composer-meta">{{ model || 'deepseek-v4-pro' }} {{ effort || 'default' }}</span>
    <button v-if="disabled" class="stop-button" title="停止" @click="$emit('stop')">停</button>
    <button v-else class="send-button" title="发送" :disabled="!draft.trim()" @click="send">↑</button>
  </footer>
</template>
