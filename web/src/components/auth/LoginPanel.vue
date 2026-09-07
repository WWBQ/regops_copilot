<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchDemoAccounts } from '../../api/auth'
import { useAuth } from '../../composables/useAuth'

const emit = defineEmits<{
  loggedIn: []
}>()

const { login } = useAuth()
const username = ref('analyst')
const password = ref('analyst123')
const submitting = ref(false)
const error = ref('')
const accounts = ref<string[]>([])

onMounted(async () => {
  try {
    accounts.value = (await fetchDemoAccounts()).accounts
  } catch {
    accounts.value = ['analyst/analyst123', 'checker/checker123', 'rm/rm123', 'admin/admin123']
  }
})

function pick(account: string) {
  const [name, pass] = account.split('/')
  username.value = name
  password.value = pass ?? ''
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await login(username.value.trim(), password.value)
    emit('loggedIn')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="login-panel" @submit.prevent="submit">
    <p class="hint">演示账号（密码已填）：点一下即可切换。</p>
    <div class="account-row">
      <button
        v-for="item in accounts"
        :key="item"
        type="button"
        class="chip"
        @click="pick(item)"
      >
        {{ item.split('/')[0] }}
      </button>
    </div>
    <label>
      用户名
      <input v-model="username" autocomplete="username" />
    </label>
    <label>
      密码
      <input v-model="password" type="password" autocomplete="current-password" />
    </label>
    <p v-if="error" class="error">{{ error }}</p>
    <button type="submit" class="primary-btn" :disabled="submitting">
      {{ submitting ? '登录中…' : '登录' }}
    </button>
  </form>
</template>

<style scoped>
.login-panel {
  display: grid;
  gap: 10px;
  max-width: 420px;
}
.hint {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
}
.account-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.chip:hover {
  background: #ecfeff;
}
label {
  display: grid;
  gap: 4px;
  font-size: 13px;
  color: var(--muted);
}
input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
}
.primary-btn {
  border: 0;
  background: #0f766e;
  color: #fff;
  border-radius: 8px;
  padding: 8px 14px;
  cursor: pointer;
}
.primary-btn:disabled {
  opacity: 0.7;
}
.error {
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
}
</style>
