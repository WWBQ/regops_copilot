<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { downloadLabelExport, getLabelTask } from '../../api/labeling'
import type { LabelItem, LabelTask } from '../../types/labeling'

const route = useRoute()
const router = useRouter()
const task = ref<LabelTask | null>(null)
const items = ref<LabelItem[]>([])
const error = ref('')
const loading = ref(true)

const taskId = computed(() => String(route.params.taskId ?? ''))

function statusLabel(status: string): string {
  return status || '未标'
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const data = await getLabelTask(taskId.value)
    task.value = data.task
    items.value = data.items
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function onExport() {
  if (!task.value) return
  try {
    await downloadLabelExport(task.value.id, task.value.name)
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
        <h1>{{ task?.name ?? '标注任务' }}</h1>
        <p v-if="task">共 {{ task.count }} 条 · {{ task.url_type }} · 进度 {{ task.progress }}%</p>
        <p v-if="task?.label_options?.length" class="hint">选项：{{ task.label_options.join(' / ') }}</p>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost-btn" @click="onExport">导出 Excel</button>
        <button type="button" class="ghost-btn" @click="router.push('/quality/review')">返回大厅</button>
      </div>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <table v-if="!loading && items.length" class="grid">
      <thead>
        <tr>
          <th>序号</th>
          <th>URL</th>
          <th>状态</th>
          <th>备注</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.index">
          <td>{{ item.index }}</td>
          <td class="url"><a :href="item.url" target="_blank" rel="noreferrer">{{ item.url }}</a></td>
          <td>
            <span :class="['status', item.status]">{{ statusLabel(item.status) }}</span>
          </td>
          <td>{{ item.notes }}</td>
          <td>
            <router-link :to="`/quality/review/${taskId}/${item.index}`">查看</router-link>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.grid {
  width: 100%;
  margin-top: 16px;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 13px;
  vertical-align: top;
}

th {
  background: #f8fafc;
  color: var(--muted);
}

.url {
  max-width: 420px;
  word-break: break-all;
}

.url a {
  color: var(--accent);
}

.status.ok {
  color: #15803d;
  font-weight: 700;
}

.status.issue {
  color: var(--danger);
  font-weight: 700;
}

.error {
  color: var(--danger);
}
</style>
