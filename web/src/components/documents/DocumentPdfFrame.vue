<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { documentContentUrl } from '../../api/documents'

const props = defineProps<{
  docId: string
  page?: number
}>()

const loadError = ref<string | null>(null)
const checking = ref(true)
let abortController: AbortController | null = null

const pdfSrc = computed(() => documentContentUrl(props.docId, props.page))

async function checkDocument() {
  abortController?.abort()
  abortController = new AbortController()
  checking.value = true
  loadError.value = null
  try {
    const response = await fetch(pdfSrc.value, {
      method: 'HEAD',
      signal: abortController.signal,
    })
    if (!response.ok) {
      loadError.value = `文档加载失败（HTTP ${response.status}）`
    }
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    loadError.value = '无法连接文档服务，请确认 Java BFF (8080) 已启动'
  } finally {
    checking.value = false
  }
}

watch(pdfSrc, () => { void checkDocument() }, { immediate: true })

onBeforeUnmount(() => abortController?.abort())
</script>

<template>
  <div v-if="checking" class="document-frame-status">正在加载 PDF…</div>
  <div v-else-if="loadError" class="document-frame-status error">
    <p>{{ loadError }}</p>
    <a :href="pdfSrc" target="_blank" rel="noopener noreferrer">在新标签页尝试打开</a>
  </div>
  <object
    v-else
    :key="pdfSrc"
    class="document-pdf-frame"
    :data="pdfSrc"
    type="application/pdf"
  >
    <p class="embed-fallback">
      当前浏览器无法内嵌预览，
      <a :href="pdfSrc" target="_blank" rel="noopener noreferrer">点击在新标签页打开 PDF</a>
    </p>
  </object>
</template>

<style scoped>
.document-frame-status {
  width: 100%;
  height: 100%;
  min-height: 220px;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 14px;
}

.document-frame-status.error {
  align-content: center;
  color: #991b1b;
  text-align: center;
  padding: 24px;
}

.document-frame-status p { margin: 0; }

.document-frame-status a,
.embed-fallback a {
  color: #0f766e;
  font-weight: 600;
}

.document-frame-status a { margin-top: 12px; }

.document-pdf-frame {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 320px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #ffffff;
}

.embed-fallback {
  padding: 24px;
  text-align: center;
  color: var(--muted);
}
</style>
