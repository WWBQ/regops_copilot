<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { listCustomers, type CustomerProfile } from '../../api/customers'
import LoginPanel from '../../components/auth/LoginPanel.vue'
import { useAuth } from '../../composables/useAuth'
import { deptLabel, roleLabel } from '../../config/user'

const { user, loggedIn, logout } = useAuth()
const customers = ref<CustomerProfile[]>([])
const loading = ref(false)
const error = ref('')

const initials = computed(() => {
  const name = user.value?.displayName ?? '未登录'
  return name.slice(-2)
})

function onLogout() {
  logout()
  customers.value = []
}

async function refresh() {
  if (!loggedIn.value) {
    customers.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    customers.value = await listCustomers()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    customers.value = []
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
        <h1>用户与数据域</h1>
        <p>
          JWT + RBAC。客户经理只能看到 <code>CLIENT</code> 档案；投研内核（比亚迪 / 长城）对客户经理返回 404，不泄露标题。
        </p>
      </div>
    </header>

    <section class="panel">
      <h2>{{ loggedIn ? '当前登录' : '登录' }}</h2>
      <template v-if="loggedIn">
        <div class="who-card">
          <span class="avatar">{{ initials }}</span>
          <dl>
            <div>
              <dt>显示名</dt>
              <dd>{{ user?.displayName }}</dd>
            </div>
            <div>
              <dt>角色 / 部门</dt>
              <dd>{{ roleLabel(user?.role) }} · {{ deptLabel(user?.dept) }}</dd>
            </div>
            <div>
              <dt>用户名</dt>
              <dd>{{ user?.username }}</dd>
            </div>
          </dl>
        </div>
        <button type="button" class="ghost-btn" @click="onLogout">退出</button>
      </template>
      <LoginPanel v-else @logged-in="refresh" />
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>客户档案（已脱敏）</h2>
        <button type="button" class="ghost-btn" :disabled="!loggedIn || loading" @click="refresh">刷新</button>
      </div>
      <p v-if="!loggedIn" class="hint">登录后按角色过滤。用 rm / rm123 应只看到美的、格力。</p>
      <p v-else-if="error" class="error">{{ error }}</p>
      <p v-else-if="loading" class="hint">加载中…</p>
      <p v-else-if="!customers.length" class="hint">没有可见档案。</p>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>分类</th>
              <th>证件</th>
              <th>电话</th>
              <th>风险</th>
              <th>部门</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in customers" :key="row.id">
              <td class="mono">{{ row.companyCode }}</td>
              <td>{{ row.displayName }}</td>
              <td>
                <span :class="row.classification === 'INTERNAL_RESEARCH' ? 'tag warn' : 'tag ok'">
                  {{ row.classification }}
                </span>
              </td>
              <td class="mono">{{ row.maskedIdNo }}</td>
              <td class="mono">{{ row.maskedPhone }}</td>
              <td>{{ row.riskLevel }}</td>
              <td>{{ deptLabel(row.dept) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.page {
  max-width: 960px;
  margin: 0 auto;
}
.head h1 {
  margin: 0 0 8px;
  font-size: 24px;
}
.head p {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 14px;
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 16px;
}
.panel h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.panel-head h2 {
  margin: 0;
}
.who-card {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 12px;
}
.avatar {
  width: 48px;
  height: 48px;
  border-radius: 999px;
  background: linear-gradient(145deg, #0f766e, #14b8a6);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
}
.who-card dl {
  display: grid;
  gap: 8px;
  margin: 0;
}
.who-card dt {
  font-size: 12px;
  color: #94a3b8;
}
.who-card dd {
  margin: 2px 0 0;
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
}
.mono {
  font-family: var(--mono);
  font-size: 12px;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.tag.ok {
  background: #ecfdf5;
  color: #047857;
}
.tag.warn {
  background: #fffbeb;
  color: #b45309;
}
.hint {
  color: var(--muted);
  font-size: 14px;
}
.error {
  color: #b91c1c;
}
</style>
