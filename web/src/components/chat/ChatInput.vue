<script setup lang="ts">
import { computed, ref } from 'vue'

import { modelLabel } from '../../utils/models'

const props = withDefaults(
  defineProps<{
    loading: boolean
    disabled?: boolean
    uploading?: boolean
    models?: string[]
    model?: string
    backendOk?: boolean | null
  }>(),
  {
    models: () => [],
    model: '',
    backendOk: null,
  },
)

const emit = defineEmits<{
  send: [message: string]
  attach: [file: File]
  'update:model': [model: string]
}>()

const draft = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const canSend = computed(
  () => !props.loading && !props.uploading && draft.value.trim().length > 0,
)

const hasModels = computed(() => props.models.length > 0)

const statusDotClass = computed(() => {
  if (props.backendOk === true) {
    return 'ok'
  }
  if (props.backendOk === false) {
    return 'bad'
  }
  return 'idle'
})

const statusTitle = computed(() => {
  if (props.backendOk === true) {
    return '服务已连接'
  }
  if (props.backendOk === false) {
    return '服务不可用'
  }
  return '正在检测连接…'
})

function submit() {
  const text = draft.value.trim()
  if (!text || !canSend.value) {
    return
  }
  emit('send', text)
  draft.value = ''
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}

function openFilePicker() {
  if (props.loading || props.uploading) {
    return
  }
  fileInputRef.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    window.alert('目前仅支持 PDF 文件')
    return
  }
  emit('attach', file)
}

function onModelChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  emit('update:model', value)
}
</script>

<template>
  <div class="composer">
    <div class="composer-row">
      <button
        type="button"
        class="attach-btn"
        title="上传 PDF（本会话有效）"
        :disabled="loading || uploading"
        @click="openFilePicker"
      >
        {{ uploading ? '…' : '📎' }}
      </button>
      <input
        ref="fileInputRef"
        type="file"
        accept=".pdf,application/pdf"
        class="hidden-file"
        @change="onFileChange"
      />

      <textarea
        v-model="draft"
        class="composer-input"
        rows="1"
        placeholder="输入合规/监管或年报相关问题，Enter 发送"
        :disabled="loading || uploading"
        @keydown="onKeydown"
      />

      <label class="model-select-wrap" :title="statusTitle">
        <span class="status-dot" :class="statusDotClass" aria-hidden="true" />
        <select
          v-if="hasModels"
          class="model-select"
          :value="model"
          :disabled="loading || uploading"
          @change="onModelChange"
        >
          <option v-for="item in models" :key="item" :value="item">
            {{ modelLabel(item) }}
          </option>
        </select>
        <span v-else class="model-unavailable">无模型</span>
      </label>

      <button type="button" class="send-btn" :disabled="!canSend" @click="submit">
        {{ loading ? '…' : '发送' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.composer-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.attach-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  background: white;
  color: var(--text);
  border-radius: 10px;
  font-size: 16px;
  cursor: pointer;
}

.attach-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.attach-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.model-select-wrap {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  background: white;
  border-radius: 10px;
  padding: 0 10px;
  height: 36px;
  max-width: 140px;
  cursor: default;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #64748b;
}

.status-dot.ok {
  background: #22c55e;
}

.status-dot.bad {
  background: #dc2626;
}

.status-dot.idle {
  background: #eab308;
}

.model-unavailable {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.model-select {
  border: none;
  background: transparent;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  min-width: 0;
  max-width: 110px;
}

.model-select:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.hidden-file {
  display: none;
}

.send-btn {
  flex-shrink: 0;
  height: 36px;
  padding: 0 14px;
}

@media (max-width: 640px) {
  .composer-row {
    flex-wrap: wrap;
  }

  .composer-input {
    order: 2;
    flex: 1 1 100%;
  }

  .attach-btn {
    order: 1;
  }

  .model-select-wrap {
    order: 3;
    max-width: none;
    flex: 1;
  }

  .send-btn {
    order: 4;
  }
}
</style>
