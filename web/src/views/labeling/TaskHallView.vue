<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { downloadLabelExport, listLabelTasks } from '../../api/labeling'
import type { LabelTask } from '../../types/labeling'

const router = useRouter()
const tasks = ref<LabelTask[]>([])
const error = ref('')
const loading = ref(true)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    tasks.value = await listLabelTasks()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function onExport(task: LabelTask) {
  try {
    await downloadLabelExport(task.id, task.name)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '导出失败'
  }
}

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="chat-header">
      <div>
        <h1>数据标注</h1>
        <p>上传 Excel / JSON，核对 PDF、HTML 或文本，标注结果可导出。问 AI 走 python-ai <code>POST /chat</code>。</p>
      </div>
      <button type="button" class="send-btn" @click="router.push('/quality/review/create')">创建任务</button>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="!loading && !tasks.length" class="hint">还没有任务。点击右上角创建，并上传按标准模板填写的 .xlsx。</p>

    <div class="task-grid">
      <article v-for="task in tasks" :key="task.id" class="task-card">
        <h2>{{ task.name }}</h2>
        <p class="desc">{{ task.desc || '无描述' }}</p>
        <p class="meta">{{ task.count }} 条 · {{ task.url_type }} · {{ task.created_at }}</p>
        <div class="bar">
          <span class="bar-fill" :style="{ width: `${task.progress}%` }" />
        </div>
        <p class="meta">进度 {{ task.progress }}%</p>
        <div class="actions">
          <button type="button" class="ghost-btn" @click="onExport(task)">导出</button>
          <button type="button" class="send-btn" @click="router.push(`/quality/review/${task.id}`)">进入</button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.task-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
  box-shadow: var(--shadow);
}

.task-card h2 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--text-strong);
}

.desc,
.meta {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 13px;
}

.bar {
  height: 8px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
  margin: 10px 0 6px;
}

.bar-fill {
  display: block;
  height: 100%;
  background: var(--accent);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.error {
  color: var(--danger);
}
</style>
