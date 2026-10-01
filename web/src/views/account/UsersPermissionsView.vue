<script setup lang="ts">
import { computed } from 'vue'

import LoginPanel from '../../components/auth/LoginPanel.vue'
import { useAuth } from '../../composables/useAuth'
import { deptLabel, roleLabel } from '../../config/user'

const { user, loggedIn, logout } = useAuth()

const initials = computed(() => (user.value?.displayName ?? '未登录').slice(-2))
const companyScope = computed(() => {
  if (user.value?.dept === 'research') return '002594 比亚迪、601633 长城汽车'
  if (user.value?.dept === 'rm') return '000333 美的集团、000651 格力电器'
  if (user.value?.dept === 'compliance') return '全部已配置公司年报'
  return '登录后显示'
})
</script>

<template>
  <section class="page">
    <header class="head">
      <h1>用户与数据权限</h1>
      <p>JWT 确认用户身份，部门数据域限制年报检索、引用和原文预览。</p>
    </header>

    <section class="panel">
      <h2>{{ loggedIn ? '当前登录' : '登录' }}</h2>
      <template v-if="loggedIn">
        <div class="who-card">
          <span class="avatar">{{ initials }}</span>
          <dl>
            <div><dt>显示名</dt><dd>{{ user?.displayName }}</dd></div>
            <div><dt>角色 / 部门</dt><dd>{{ roleLabel(user?.role) }} · {{ deptLabel(user?.dept) }}</dd></div>
            <div><dt>用户名</dt><dd>{{ user?.username }}</dd></div>
          </dl>
        </div>
        <button type="button" class="ghost-btn" @click="logout">退出</button>
      </template>
      <LoginPanel v-else />
    </section>

    <section class="panel">
      <h2>当前年报数据域</h2>
      <div class="scope-card">
        <span class="scope-label">允许公司</span>
        <strong>{{ companyScope }}</strong>
      </div>
      <ul class="rules">
        <li>Java BFF 从已验证的 JWT 取得部门，不接受前端自行指定权限。</li>
        <li>Python 在检索前按部门裁剪 doc_id，未授权内容不会进入 Prompt。</li>
        <li>会话中由本人上传的 PDF 不受公司白名单限制。</li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.page { max-width: 820px; margin: 0 auto; }
.head h1 { margin: 0 0 8px; font-size: 24px; }
.head p { margin: 0 0 16px; color: var(--muted); font-size: 14px; }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; margin-bottom: 16px; }
.panel h2 { margin: 0 0 14px; font-size: 16px; }
.who-card { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; }
.avatar { width: 48px; height: 48px; border-radius: 999px; background: linear-gradient(145deg, #0f766e, #14b8a6); color: #fff; display: grid; place-items: center; font-weight: 700; }
.who-card dl { display: grid; gap: 8px; margin: 0; }
.who-card dt { font-size: 12px; color: #94a3b8; }
.who-card dd { margin: 2px 0 0; }
.ghost-btn { padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; }
.scope-card { display: grid; gap: 6px; padding: 14px; border-radius: 10px; background: color-mix(in srgb, var(--surface) 85%, #14b8a6 15%); }
.scope-label { color: var(--muted); font-size: 12px; }
.rules { margin: 14px 0 0; padding-left: 20px; color: var(--muted); line-height: 1.8; font-size: 14px; }
</style>
