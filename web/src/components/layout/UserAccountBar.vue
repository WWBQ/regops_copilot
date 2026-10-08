<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuth } from '../../composables/useAuth'
import { deptLabel, GUEST_USER, roleLabel, userInitials } from '../../config/user'

const router = useRouter()
const { user, loggedIn, logout } = useAuth()

const profileOpen = ref(false)
const barRef = ref<HTMLElement | null>(null)

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

function toggleProfile() {
  profileOpen.value = !profileOpen.value
}

function closeProfile() {
  profileOpen.value = false
}

function openProfilePage() {
  closeProfile()
  void router.push('/account/profile')
}

function openPermissions() {
  closeProfile()
  void router.push('/settings/users')
}

function onLogout() {
  logout()
  closeProfile()
  void router.push('/login')
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as Node
  if (barRef.value && !barRef.value.contains(target)) {
    closeProfile()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div ref="barRef" class="user-bar">
    <button
      type="button"
      class="icon-btn"
      title="用户与权限"
      aria-label="用户与权限"
      @click.stop="openPermissions"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path
          fill="currentColor"
          d="M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 2.18 7 3.11v5.71c0 4.54-3.07 8.83-7 9.93-3.93-1.1-7-5.39-7-9.93V6.29l7-3.11zM11 7v2H8v2h3v3h2v-3h3v-2h-3V7h-2z"
        />
      </svg>
    </button>

    <div class="avatar-wrap">
      <button
        type="button"
        class="avatar-btn"
        :aria-expanded="profileOpen"
        aria-haspopup="true"
        aria-label="个人资料"
        @click.stop="toggleProfile"
      >
        <span class="avatar">{{ initials }}</span>
      </button>

      <Transition name="profile-drop">
        <div v-if="profileOpen" class="profile-panel" @click.stop>
          <div class="profile-head">
            <span class="avatar avatar-lg">{{ initials }}</span>
            <div class="profile-meta">
              <p class="profile-name">{{ display.displayName }}</p>
              <p class="profile-role">{{ display.role }}</p>
            </div>
          </div>
          <dl class="profile-fields">
            <div>
              <dt>用户名</dt>
              <dd>{{ display.username }}</dd>
            </div>
            <div>
              <dt>邮箱</dt>
              <dd>{{ display.email || '—' }}</dd>
            </div>
            <div>
              <dt>部门</dt>
              <dd>{{ display.department }}</dd>
            </div>
          </dl>
          <div class="profile-actions">
            <button type="button" class="panel-btn" @click="openProfilePage">个人资料</button>
            <button v-if="loggedIn" type="button" class="panel-btn subtle" @click="onLogout">退出</button>
            <button v-else type="button" class="panel-btn subtle" @click="openPermissions">登录</button>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.user-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
  flex-shrink: 0;
}

.icon-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #f8fafc;
  color: #64748b;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.icon-btn:hover {
  background: #ecfeff;
  border-color: #99f6e4;
  color: #0f766e;
}

.avatar-wrap {
  position: relative;
}

.avatar-btn {
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  border-radius: 999px;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: linear-gradient(145deg, #0f766e, #14b8a6);
  color: #ffffff;
  font-size: 12px;
  font-weight: 700;
  display: grid;
  place-items: center;
  box-shadow: 0 0 0 2px #ffffff, 0 0 0 3px #99f6e4;
}

.avatar-lg {
  width: 44px;
  height: 44px;
  font-size: 14px;
  flex-shrink: 0;
}

.profile-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 280px;
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
  padding: 14px;
  z-index: 60;
}

.profile-head {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.profile-meta {
  min-width: 0;
}

.profile-name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-strong);
}

.profile-role {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.profile-fields {
  margin: 12px 0 0;
  display: grid;
  gap: 10px;
}

.profile-fields div {
  display: grid;
  gap: 2px;
}

.profile-fields dt {
  margin: 0;
  font-size: 11px;
  color: #94a3b8;
}

.profile-fields dd {
  margin: 0;
  font-size: 13px;
  color: var(--text-strong);
  word-break: break-all;
}

.profile-actions {
  margin-top: 14px;
  display: flex;
  gap: 8px;
}

.panel-btn {
  flex: 1;
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-strong);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.panel-btn:hover {
  background: #f8fafc;
}

.panel-btn.subtle {
  color: var(--muted);
}

.profile-drop-enter-active,
.profile-drop-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.profile-drop-enter-from,
.profile-drop-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
