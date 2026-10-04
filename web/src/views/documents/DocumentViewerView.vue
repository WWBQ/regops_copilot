<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import DocumentPdfFrame from '../../components/documents/DocumentPdfFrame.vue'

const route = useRoute()
const router = useRouter()

const docId = computed(() => String(route.params.docId ?? ''))
const page = computed(() => {
  const raw = Number(route.query.page ?? 1)
  return Number.isFinite(raw) && raw > 0 ? raw : 1
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    void router.push('/')
  }
}
</script>

<template>
  <section class="doc-viewer">
    <header class="doc-viewer-header">
      <button type="button" class="back-btn" @click="goBack">← 返回</button>
      <div class="doc-meta">
        <h1>{{ docId }}</h1>
        <p>第 {{ page }} 页 · 浏览器内预览</p>
      </div>
    </header>

    <div class="doc-viewer-frame-wrap">
      <DocumentPdfFrame :doc-id="docId" :page="page" />
    </div>
  </section>
</template>

<style scoped>
.doc-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #f1f5f9;
}

.doc-viewer-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: #ffffff;
}

.back-btn {
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-strong);
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.back-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.doc-meta {
  min-width: 0;
}

.doc-meta h1 {
  margin: 0;
  font-size: 16px;
  color: var(--text-strong);
}

.doc-meta p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.doc-viewer-frame-wrap {
  flex: 1;
  min-height: 0;
  padding: 12px;
}
</style>
