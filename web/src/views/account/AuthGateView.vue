<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import LoginPanel from '../../components/auth/LoginPanel.vue'
import { useAuth } from '../../composables/useAuth'

const route = useRoute()
const router = useRouter()
const { register } = useAuth()
const registering = ref(false)
const username = ref('')
const displayName = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const submitting = ref(false)
const error = ref('')

const destination = computed(() => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
    ? redirect
    : '/'
})

function afterLogin() {
  void router.replace(destination.value)
}

async function submitRegister() {
  error.value = ''
  if (password.value !== confirmPassword.value) {
    error.value = '两次密码输入不一致'
    return
  }
  submitting.value = true
  try {
    await register(username.value.trim(), password.value, displayName.value.trim(), email.value.trim())
    afterLogin()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '注册失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <div class="brand-mark">R</div>
      <h1>RegOps Copilot</h1>
      <p class="intro">登录后使用合规问答与金融风险审计助手；对话记录会按账号保存在数据库中。</p>
      <div class="tabs" role="tablist" aria-label="登录或注册">
        <button type="button" :class="{ active: !registering }" @click="registering = false">登录</button>
        <button type="button" :class="{ active: registering }" @click="registering = true">注册</button>
      </div>
      <LoginPanel v-if="!registering" @logged-in="afterLogin" />
      <form v-else class="register-form" @submit.prevent="submitRegister">
        <label>用户名<input v-model="username" autocomplete="username" required minlength="3" maxlength="64" pattern="[A-Za-z0-9_]+" /></label>
        <label>显示名称<input v-model="displayName" autocomplete="name" required maxlength="80" /></label>
        <label>邮箱（选填）<input v-model="email" type="email" autocomplete="email" maxlength="120" /></label>
        <label>密码<input v-model="password" type="password" autocomplete="new-password" required minlength="8" maxlength="72" /></label>
        <label>确认密码<input v-model="confirmPassword" type="password" autocomplete="new-password" required minlength="8" /></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="submit-btn" type="submit" :disabled="submitting">{{ submitting ? '注册中…' : '注册并进入' }}</button>
        <p class="hint">新账号固定为投研分析师权限，不能自行选择角色或部门。</p>
      </form>
    </section>
  </main>
</template>

<style scoped>
.auth-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f3f7fa; }
.auth-card { width: min(440px, 100%); padding: 32px; border: 1px solid #dce5ee; border-radius: 20px; background: #fff; box-shadow: 0 20px 60px rgba(15, 23, 42, .09); }
.brand-mark { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; color: #fff; background: #0f766e; font-weight: 800; }
h1 { margin: 16px 0 6px; font-size: 24px; }
.intro, .hint { color: #64748b; font-size: 13px; line-height: 1.6; }
.tabs { display: flex; gap: 8px; margin: 24px 0 18px; }
.tabs button { flex: 1; padding: 10px; border: 1px solid #dce5ee; background: #f8fafc; border-radius: 8px; cursor: pointer; }
.tabs button.active { color: #0f766e; background: #ecfdf5; border-color: #5eead4; font-weight: 700; }
.register-form, .register-form label { display: grid; gap: 7px; }
.register-form { gap: 13px; }
.register-form label { color: #475569; font-size: 13px; }
.register-form input { padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; }
.submit-btn { border: 0; border-radius: 8px; padding: 11px; background: #0f766e; color: white; cursor: pointer; }
.error { color: #b91c1c; font-size: 13px; margin: 0; }
.hint { margin: 0; }
</style>
