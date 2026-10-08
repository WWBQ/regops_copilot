<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

import { fetchDocumentPdf } from '../../api/documentPdf'

const props = defineProps<{
  docId: string
  page?: number
}>()

const emit = defineEmits<{ pageChange: [page: number] }>()

const document = shallowRef<PDFDocumentProxy | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const pageArea = ref<HTMLElement | null>(null)
const currentPage = ref(1)
const pageCount = ref(0)
const loading = ref(true)
const rendering = ref(false)
const loadError = ref<string | null>(null)

let abortController: AbortController | null = null
let loadingTask: PDFDocumentLoadingTask | null = null
let renderTask: RenderTask | null = null
let resizeObserver: ResizeObserver | null = null
let requestId = 0
let renderId = 0

const canGoBack = computed(() => currentPage.value > 1)
const canGoForward = computed(() => currentPage.value < pageCount.value)

function cancelRender() {
  renderId += 1
  renderTask?.cancel()
  renderTask = null
}

async function renderPage() {
  const pdf = document.value
  const target = canvas.value
  const area = pageArea.value
  if (!pdf || !target || !area) return

  cancelRender()
  const currentRender = renderId
  rendering.value = true
  loadError.value = null
  try {
    const page = await pdf.getPage(currentPage.value)
    if (currentRender !== renderId) return

    const unscaled = page.getViewport({ scale: 1 })
    const availableWidth = Math.max(240, area.clientWidth - 24)
    const scale = availableWidth / unscaled.width
    const viewport = page.getViewport({ scale })
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
    target.width = Math.ceil(viewport.width * pixelRatio)
    target.height = Math.ceil(viewport.height * pixelRatio)
    target.style.width = `${Math.ceil(viewport.width)}px`
    target.style.height = `${Math.ceil(viewport.height)}px`

    const task = page.render({
      canvas: target,
      viewport,
      transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
    })
    renderTask = task
    await task.promise
    if (currentRender === renderId) renderTask = null
  } catch (cause) {
    if (currentRender !== renderId || (cause instanceof Error && cause.name === 'RenderingCancelledException')) return
    loadError.value = cause instanceof Error ? `PDF 页面渲染失败：${cause.message}` : 'PDF 页面渲染失败'
  } finally {
    if (currentRender === renderId) rendering.value = false
  }
}

async function loadDocument(docId: string) {
  const currentRequest = ++requestId
  abortController?.abort()
  loadingTask?.destroy()
  loadingTask = null
  cancelRender()
  document.value = null
  abortController = new AbortController()
  pageCount.value = 0
  loading.value = true
  loadError.value = null

  try {
    const blob = await fetchDocumentPdf(docId, abortController.signal)
    const bytes = new Uint8Array(await blob.arrayBuffer())
    if (currentRequest !== requestId) return
    const pdfjs = await import('pdfjs-dist')
    if (currentRequest !== requestId) return
    pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl
    const task = pdfjs.getDocument({ data: bytes, useSystemFonts: true })
    loadingTask = task
    const pdf = await task.promise
    if (currentRequest !== requestId) {
      void task.destroy()
      return
    }
    document.value = pdf
    pageCount.value = pdf.numPages
    currentPage.value = Math.min(Math.max(props.page || 1, 1), pdf.numPages)
    loading.value = false
    await nextTick()
    void renderPage()
  } catch (cause) {
    if (currentRequest !== requestId || (cause instanceof DOMException && cause.name === 'AbortError')) return
    loadError.value = cause instanceof Error ? cause.message : '无法加载年报 PDF'
  } finally {
    if (currentRequest === requestId) loading.value = false
  }
}

function goToPage(page: number) {
  if (!document.value || !Number.isSafeInteger(page) || page < 1 || page > pageCount.value) return
  if (page === currentPage.value) return
  currentPage.value = page
  pageArea.value?.scrollTo({ top: 0 })
  emit('pageChange', page)
}

watch(() => props.docId, (docId) => { void loadDocument(docId) }, { immediate: true })
watch(() => props.page, (page) => {
  if (document.value) goToPage(Math.min(Math.max(page || 1, 1), pageCount.value))
}, { immediate: true })
watch(currentPage, () => { void renderPage() }, { flush: 'post' })

onMounted(() => {
  resizeObserver = new ResizeObserver(() => { void renderPage() })
  if (pageArea.value) resizeObserver.observe(pageArea.value)
})

onBeforeUnmount(() => {
  requestId += 1
  abortController?.abort()
  resizeObserver?.disconnect()
  cancelRender()
  loadingTask?.destroy()
})
</script>

<template>
  <div class="pdf-viewer">
    <div class="pdf-toolbar">
      <button type="button" :disabled="!canGoBack" aria-label="上一页" @click="goToPage(currentPage - 1)">‹</button>
      <span>第 {{ currentPage }} / {{ pageCount || '—' }} 页</span>
      <button type="button" :disabled="!canGoForward" aria-label="下一页" @click="goToPage(currentPage + 1)">›</button>
    </div>
    <div ref="pageArea" class="pdf-page-area">
      <p v-if="loading" class="pdf-state">正在加载 PDF…</p>
      <p v-if="loadError" class="pdf-state error">{{ loadError }}</p>
      <p v-if="rendering && !loadError" class="pdf-state rendering">正在绘制第 {{ currentPage }} 页…</p>
      <canvas ref="canvas" class="pdf-canvas" :class="{ hidden: loading || Boolean(loadError) }" />
    </div>
  </div>
</template>

<style scoped>
.pdf-viewer { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 320px; border: 1px solid var(--border); border-radius: 12px; background: #f1f5f9; overflow: hidden; }
.pdf-toolbar { display: flex; align-items: center; justify-content: center; gap: 12px; flex: 0 0 auto; min-height: 44px; border-bottom: 1px solid var(--border); background: #fff; font-size: 13px; color: var(--text-strong); }
.pdf-toolbar button { width: 30px; height: 30px; border: 1px solid var(--border); border-radius: 6px; background: #fff; cursor: pointer; font-size: 20px; line-height: 1; }
.pdf-toolbar button:disabled { opacity: .4; cursor: default; }
.pdf-page-area { flex: 1; min-height: 0; overflow: auto; padding: 12px; text-align: center; }
.pdf-canvas { display: block; max-width: 100%; height: auto; margin: 0 auto; background: #fff; box-shadow: 0 2px 10px #17264020; }
.pdf-canvas.hidden { visibility: hidden; height: 0 !important; }
.pdf-state { margin: 32px auto; font-size: 13px; color: var(--text-muted); }
.pdf-state.error { color: #991b1b; overflow-wrap: anywhere; }
.pdf-state.rendering { margin: 8px auto; }
</style>
