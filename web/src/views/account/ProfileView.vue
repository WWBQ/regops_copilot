<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import LoginPanel from '../../components/auth/LoginPanel.vue'
import { useAuth } from '../../composables/useAuth'
import { deptLabel, GUEST_USER, roleLabel, userInitials } from '../../config/user'

const router = useRouter()
const { user, loggedIn, logout } = useAuth()
function signOut() { logout(); void router.replace('/login') }

const display = computed(() => {
  if (!user.value) return GUEST_USER
  return {
    id: user.value.id,
    displayName: user.value.displayName,
    username: user.value.username,
    email: user.value.email,
    role: roleLabel(user.value.role),
    department: deptLabel(user.value.dept),
  }
})

const initials = computed(() => userInitials(display.value.displayName))
</script>

<template>
  <section class="profile-page">
    <header class="profile-card">
      <div class="profile-hero">
        <span class="avatar">{{ initials }}</span>
        <div>
          <h1>个人资料</h1>
          <p class="subtitle">{{ display.displayName }} · {{ display.role }}</p>
        </div>
      </div>
    </header>

    <div v-if="!loggedIn" class="profile-card">
      <h2>登录</h2>
      <p class="hint">演示账号：analyst / rm / admin，密码均为用户名 + 123。</p>
      <LoginPanel />
    </div>

    <div v-else class="profile-card">
      <h2>基本信息</h2>
      <dl class="info-grid">
        <div>
          <dt>显示名称</dt>
          <dd>{{ display.displayName }}</dd>
        </div>
        <div>
          <dt>用户名</dt>
          <dd>{{ display.username }}</dd>
        </div>
        <div>
          <dt>邮箱</dt>
          <dd>{{ display.email || '—' }}</dd>
        </div>
        <div>
          <dt>角色</dt>
          <dd>{{ display.role }}</dd>
        </div>
        <div>
          <dt>部门</dt>
          <dd>{{ display.department }}</dd>
        </div>
        <div>
          <dt>用户 ID</dt>
          <dd><code>{{ display.id }}</code></dd>
        </div>
      </dl>
      <p class="hint">JWT 存在浏览器本地。受保护的年报数据域和审计接口会校验角色与部门。</p>
    </div>

    <div class="profile-actions">
      <button type="button" class="ghost-btn" @click="router.push('/settings/users')">
        用户与权限
      </button>
      <button v-if="loggedIn" type="button" class="ghost-btn" @click="signOut">退出</button>
      <button type="button" class="ghost-btn" @click="router.push('/')">返回问答</button>
    </div>
  </section>
</template>

<style scoped>
.profile-page {
  max-width: 720px;
  margin: 0 auto;
  display: grid;
  gap: 16px;
}

.profile-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
}

.profile-hero {
  display: flex;
  gap: 16px;
  align-items: center;
}

.avatar {
  width: 56px;
  height: 56px;
  border-radius: 999px;
  background: linear-gradient(145deg, #0f766e, #14b8a6);
  color: #ffffff;
  font-size: 18px;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.profile-hero h1 {
  margin: 0;
  font-size: 24px;
  color: var(--text-strong);
}

.subtitle {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 14px;
}

.profile-card h2 {
  margin: 0 0 16px;
  font-size: 16px;
  color: var(--text-strong);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin: 0;
}

.info-grid div {
  display: grid;
  gap: 4px;
}

.info-grid dt {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}

.info-grid dd {
  margin: 0;
  font-size: 14px;
  color: var(--text-strong);
}

.hint {
  margin: 18px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.profile-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.ghost-btn {
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-strong);
  border-radius: 10px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover {
  background: #f8fafc;
}
</style>
