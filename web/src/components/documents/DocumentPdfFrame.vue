<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { documentViewerPage } from '../../api/documents'
import { fetchDocumentPdf } from '../../api/documentPdf'

const props = defineProps<{
  docId: string
  page?: number
}>()

const loadError = ref<string | null>(null)
const checking = ref(true)
let abortController: AbortController | null = null
let requestId = 0
const objectUrl = ref<string | null>(null)

const pdfSrc = computed(() => {
  if (!objectUrl.value) return ''
  return props.page && props.page > 0 ? `${objectUrl.value}#page=${props.page}` : objectUrl.value
})
const viewerHref = computed(() => documentViewerPage(props.docId, props.page))

function releaseObjectUrl() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = null
  }
}

async function checkDocument() {
  const currentRequest = ++requestId
  abortController?.abort()
  abortController = new AbortController()
  releaseObjectUrl()
  checking.value = true
  loadError.value = null
  try {
    const blob = await fetchDocumentPdf(props.docId, abortController.signal)
    if (currentRequest !== requestId) return
    objectUrl.value = URL.createObjectURL(blob)
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') return
    if (currentRequest === requestId) {
      loadError.value = cause instanceof Error ? cause.message : '无法加载年报 PDF'
    }
  } finally {
    if (currentRequest === requestId) checking.value = false
  }
}

watch(() => props.docId, () => { void checkDocument() }, { immediate: true })

onBeforeUnmount(() => {
  requestId += 1
  abortController?.abort()
  releaseObjectUrl()
})
</script>

<template>
  <div v-if="checking" class="document-frame-status">正在加载 PDF…</div>
  <div v-else-if="loadError" class="document-frame-status error">
    <p>{{ loadError }}</p>
    <a :href="viewerHref" target="_blank" rel="noopener noreferrer">在新标签页尝试打开</a>
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
      <a :href="viewerHref" target="_blank" rel="noopener noreferrer">点击在新标签页打开 PDF</a>
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
