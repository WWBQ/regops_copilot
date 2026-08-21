<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { PLACEHOLDER_PAGES } from '../config/nav'

const route = useRoute()

const page = computed(() => PLACEHOLDER_PAGES[String(route.meta.pageId ?? '')])

const links = computed(() => {
  const items: { label: string; path: string }[] = []
  if (route.meta.group === 'ops') {
    items.push(
      { label: '解析监控', path: '/ops/ingest' },
      { label: 'RAG 检索监控', path: '/ops/rag' },
      { label: '评估报告', path: '/ops/eval' },
      { label: '系统健康', path: '/ops/health' },
    )
  }
  if (route.meta.group === 'quality') {
    items.push({ label: '数据标注', path: '/quality/review' })
  }
  return items.filter((item) => item.path !== route.path).slice(0, 3)
})
</script>

<template>
  <section v-if="page" class="placeholder">
    <header class="placeholder-head">
      <p class="phase">{{ page.phase }}</p>
      <h1>{{ page.title }}</h1>
      <p class="summary">{{ page.summary }}</p>
      <p v-if="page.backend" class="backend">
        后端：<code>{{ page.backend }}</code>
      </p>
    </header>

    <div class="placeholder-card">
      <p class="hint">页面框架占位 · 功能开发中</p>
      <ul v-if="links.length" class="related">
        <li v-for="item in links" :key="item.path">
          <router-link :to="item.path">{{ item.label }}</router-link>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.placeholder {
  max-width: 720px;
  margin: 0 auto;
}

.placeholder-head {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
}

.phase {
  display: inline-block;
  margin: 0 0 10px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #ecfeff;
  color: #0f766e;
  font-size: 12px;
  font-weight: 600;
}

.placeholder-head h1 {
  margin: 0 0 8px;
  font-size: 24px;
  color: var(--text-strong);
}

.summary {
  margin: 0;
  color: var(--muted);
  line-height: 1.6;
}

.backend {
  margin: 14px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.placeholder-card {
  margin-top: 16px;
  padding: 20px 24px;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  background: #fafbfc;
}

.hint {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}

.related {
  margin: 14px 0 0;
  padding-left: 1.2em;
  color: var(--text);
}

.related a {
  color: var(--accent);
}
</style>
