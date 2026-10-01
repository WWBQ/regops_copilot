<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listAuditEvents, type AuditEvent } from '../../api/audit'
import LoginPanel from '../../components/auth/LoginPanel.vue'
import { useAuth } from '../../composables/useAuth'
import { deptLabel, roleLabel } from '../../config/user'

const { user, loggedIn } = useAuth()
const events = ref<AuditEvent[]>([])
const loading = ref(false)
const error = ref('')

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString('zh-CN')
  } catch {
    return value
  }
}

async function refresh() {
  if (!loggedIn.value) return
  loading.value = true
  error.value = ''
  try {
    events.value = await listAuditEvents()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    events.value = []
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>审计追踪</h1>
        <p>
          系统操作留下操作人、角色、部门、原因、前后快照和 <code>X-Request-ID</code>。
          客户经理不能看这条链路。本页只打 Java，不经过 python-ai。
        </p>
      </div>
      <button type="button" class="ghost-btn" :disabled="!loggedIn || loading" @click="refresh">刷新</button>
    </header>

    <nav class="quick-links">
      <router-link to="/settings/users" class="quick-link">登录 / 数据权限</router-link>
    </nav>

    <section v-if="!loggedIn" class="panel">
      <h2>先登录</h2>
      <LoginPanel @logged-in="refresh" />
    </section>

    <section v-else class="panel">
      <p class="who">当前：{{ user?.displayName }} · {{ roleLabel(user?.role) }} · {{ deptLabel(user?.dept) }}</p>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-else-if="loading" class="hint">加载中…</p>
      <p v-else-if="!events.length" class="hint">暂无审计事件。先在复核页走一遍创建 / 提交 / 通过。</p>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>动作</th>
              <th>操作人</th>
              <th>部门</th>
              <th>对象</th>
              <th>原因</th>
              <th>前后</th>
              <th>关联 ID</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in events" :key="row.id">
              <td>{{ formatTime(row.occurredAt) }}</td>
              <td>{{ row.action }}</td>
              <td>{{ row.actorUsername }} / {{ row.actorRole }}</td>
              <td>{{ deptLabel(row.dept) }}</td>
              <td class="mono">{{ row.entityType }} {{ row.entityId.slice(0, 8) }}</td>
              <td>{{ row.reason || '—' }}</td>
              <td class="mono">{{ row.beforeJson || '—' }} → {{ row.afterJson || '—' }}</td>
              <td class="mono">{{ row.requestId || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
}
.head h1 {
  margin: 0 0 8px;
  font-size: 24px;
}
.head p {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  max-width: 720px;
}
.quick-links {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.quick-link {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
  color: #2563eb;
  text-decoration: none;
  background: var(--surface);
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
.who,
.hint {
  color: var(--muted);
  font-size: 13px;
}
.error {
  color: #b91c1c;
}
.ghost-btn {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
}
.table-wrap {
  overflow: auto;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
.mono {
  font-family: var(--mono);
  font-size: 12px;
}
</style>
