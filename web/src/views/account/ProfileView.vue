<script setup lang="ts">
import { useRouter } from 'vue-router'

import { CURRENT_USER, userInitials } from '../../config/user'

const router = useRouter()
const initials = userInitials(CURRENT_USER.displayName)
</script>

<template>
  <section class="profile-page">
    <header class="profile-card">
      <div class="profile-hero">
        <span class="avatar">{{ initials }}</span>
        <div>
          <h1>个人资料</h1>
          <p class="subtitle">{{ CURRENT_USER.displayName }} · {{ CURRENT_USER.role }}</p>
        </div>
      </div>
    </header>

    <div class="profile-card">
      <h2>基本信息</h2>
      <dl class="info-grid">
        <div>
          <dt>显示名称</dt>
          <dd>{{ CURRENT_USER.displayName }}</dd>
        </div>
        <div>
          <dt>用户名</dt>
          <dd>{{ CURRENT_USER.username }}</dd>
        </div>
        <div>
          <dt>邮箱</dt>
          <dd>{{ CURRENT_USER.email }}</dd>
        </div>
        <div>
          <dt>角色</dt>
          <dd>{{ CURRENT_USER.role }}</dd>
        </div>
        <div>
          <dt>部门</dt>
          <dd>{{ CURRENT_USER.department }}</dd>
        </div>
        <div>
          <dt>用户 ID</dt>
          <dd><code>{{ CURRENT_USER.id }}</code></dd>
        </div>
      </dl>
      <p class="hint">W9+ 接入统一认证与 RBAC 后可在此编辑资料。</p>
    </div>

    <div class="profile-actions">
      <button type="button" class="ghost-btn" @click="router.push('/settings/users')">
        用户与权限
      </button>
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
