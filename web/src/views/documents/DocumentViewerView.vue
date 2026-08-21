<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { documentContentUrl } from '../../api/documents'

const route = useRoute()
const router = useRouter()

const loadError = ref<string | null>(null)
const checking = ref(true)

const docId = computed(() => String(route.params.docId ?? ''))
const page = computed(() => {
  const raw = Number(route.query.page ?? 1)
  return Number.isFinite(raw) && raw > 0 ? raw : 1
})

const pdfSrc = computed(() => documentContentUrl(docId.value, page.value))

onMounted(async () => {
  try {
    const response = await fetch(pdfSrc.value, { method: 'HEAD' })
    if (!response.ok) {
      loadError.value = `文档加载失败（HTTP ${response.status}）`
    }
  } catch {
    loadError.value = '无法连接文档服务，请确认 Java BFF (8080) 已启动'
  } finally {
    checking.value = false
  }
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

    <div v-if="checking" class="doc-viewer-status">正在加载 PDF…</div>
    <div v-else-if="loadError" class="doc-viewer-status error">
      <p>{{ loadError }}</p>
      <a class="retry-link" :href="pdfSrc" target="_blank" rel="noopener noreferrer">在新标签页尝试打开</a>
    </div>

    <div v-else class="doc-viewer-frame-wrap">
      <object
        class="doc-viewer-frame"
        :data="pdfSrc"
        type="application/pdf"
      >
        <p class="embed-fallback">
          当前浏览器无法内嵌预览，
          <a :href="pdfSrc" target="_blank" rel="noopener noreferrer">点击在新标签页打开 PDF</a>
        </p>
      </object>
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

.doc-viewer-status {
  flex: 1;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 14px;
}

.doc-viewer-status.error {
  color: #991b1b;
  text-align: center;
  padding: 24px;
}

.retry-link {
  display: inline-block;
  margin-top: 12px;
  color: #0f766e;
  font-weight: 600;
}

.doc-viewer-frame-wrap {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.doc-viewer-frame {
  width: 100%;
  height: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #ffffff;
}

.embed-fallback {
  padding: 24px;
  text-align: center;
  color: var(--muted);
}

.embed-fallback a {
  color: #0f766e;
  font-weight: 600;
}
</style>
