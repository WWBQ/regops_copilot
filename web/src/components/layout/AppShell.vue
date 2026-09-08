<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, provide, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import PageSidebar from './PageSidebar.vue'
import UserAccountBar from './UserAccountBar.vue'
import { NAV_GROUPS, type NavItem } from '../../config/nav'
import { CHAT_BRIDGE_KEY, createEmptyChatBridge } from '../../composables/chatBridge'
import { SERVICE_HEALTH_KEY } from '../../composables/useServiceHealth'

const route = useRoute()
const router = useRouter()

const chatBridge = ref(createEmptyChatBridge())
provide(CHAT_BRIDGE_KEY, chatBridge)

const health = inject(SERVICE_HEALTH_KEY, null)
const javaDown = computed(() => health?.javaOk.value === false)
const pythonDegraded = computed(
  () => health?.javaOk.value === true && health?.pythonOk.value === false,
)

const headerRef = ref<HTMLElement | null>(null)
const hoverOpen = ref(false)
const clickOpen = ref(false)
let hoverCloseTimer: ReturnType<typeof setTimeout> | null = null

const menuOpen = computed(() => hoverOpen.value || clickOpen.value)

function clearHoverCloseTimer() {
  if (hoverCloseTimer) {
    clearTimeout(hoverCloseTimer)
    hoverCloseTimer = null
  }
}

function onMenuHoverEnter() {
  clearHoverCloseTimer()
  hoverOpen.value = true
}

function onMenuHoverLeave() {
  clearHoverCloseTimer()
  hoverCloseTimer = setTimeout(() => {
    hoverOpen.value = false
    hoverCloseTimer = null
  }, 120)
}

function isActive(item: NavItem): boolean {
  if (item.path === '/') {
    return route.path === '/'
  }
  return route.path === item.path || route.path.startsWith(`${item.path}/`)
}

function closeMenu() {
  clearHoverCloseTimer()
  hoverOpen.value = false
  clickOpen.value = false
}

function toggleMenu() {
  clickOpen.value = !clickOpen.value
  if (!clickOpen.value) {
    hoverOpen.value = false
  }
}

function onNavClick(item: NavItem) {
  if (item.enabled === false) {
    return
  }
  router.push(item.path)
  closeMenu()
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as Node
  if (headerRef.value && !headerRef.value.contains(target)) {
    closeMenu()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  clearHoverCloseTimer()
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div class="shell">
    <header ref="headerRef" class="topbar">
      <div class="topbar-row">
        <div class="brand">
          <div class="brand-mark">R</div>
          <div class="brand-text">
            <p class="brand-title topbar-title">RegOps Copilot</p>
            <p class="brand-sub topbar-sub">审慎监管 · 合规助手</p>
          </div>
        </div>

        <button
          type="button"
          class="menu-trigger"
          :class="{ active: menuOpen }"
          aria-label="打开功能导航"
          aria-haspopup="true"
          :aria-expanded="menuOpen"
          @mouseenter="onMenuHoverEnter"
          @mouseleave="onMenuHoverLeave"
          @click.stop="toggleMenu"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path fill="currentColor" d="M4 7h16v2H4V7zm0 5h16v2H4v-2zm0 5h16v2H4v-2z" />
          </svg>
          <span>功能导航</span>
        </button>

        <div class="topbar-right">
          <UserAccountBar />
        </div>
      </div>

      <Transition name="menu-drop">
        <div
          v-if="menuOpen"
          class="top-menu-panel"
          @mouseenter="onMenuHoverEnter"
          @mouseleave="onMenuHoverLeave"
          @click.stop
        >
          <nav class="menu-columns">
            <section v-for="group in NAV_GROUPS" :key="group.id" class="menu-column">
              <p class="menu-group-label">{{ group.label }}</p>
              <div class="menu-items-row">
                <button
                  v-for="item in group.items"
                  :key="item.id"
                  type="button"
                  class="menu-item"
                  :class="{
                    active: isActive(item),
                    disabled: item.enabled === false,
                    placeholder: item.enabled !== true,
                  }"
                  @click="onNavClick(item)"
                >
                  <span class="menu-item-label">{{ item.label }}</span>
                  <span v-if="item.phase && item.enabled !== true" class="menu-item-phase">
                    {{ item.phase }}
                  </span>
                </button>
              </div>
            </section>
          </nav>
        </div>
      </Transition>
    </header>

    <div v-if="javaDown" class="degrade-banner bad" role="status">
      Java BFF 连不上。登录、复核、审计也会失败。
    </div>
    <div v-else-if="pythonDegraded" class="degrade-banner warn" role="status">
      问答 / 问数暂不可用。
      <router-link to="/compliance/review">合规复核</router-link>
      ·
      <router-link to="/compliance/audit">审计追踪</router-link>
      仍可用。
    </div>

    <div class="shell-body">
      <PageSidebar />
      <main class="main">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.degrade-banner {
  flex-shrink: 0;
  padding: 8px 20px;
  font-size: 13px;
  line-height: 1.45;
}

.degrade-banner.warn {
  background: #fffbeb;
  color: #92400e;
  border-bottom: 1px solid #fde68a;
}

.degrade-banner.bad {
  background: #fef2f2;
  color: #991b1b;
  border-bottom: 1px solid #fecaca;
}

.degrade-banner a {
  color: inherit;
  font-weight: 700;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 50;
  background: #ffffff;
  color: var(--text);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 0 rgba(15, 23, 42, 0.04);
  isolation: isolate;
}

.topbar-row {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
  background: #ffffff;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

.brand-text {
  min-width: 0;
}

.topbar-title {
  color: var(--text-strong) !important;
}

.topbar-sub {
  color: var(--muted) !important;
}

.menu-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #f8fafc;
  color: var(--text-strong);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.menu-trigger:hover,
.menu-trigger.active {
  background: #ecfeff;
  border-color: #99f6e4;
  color: #0f766e;
}

.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.shell-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.top-menu-panel {
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  z-index: 3;
  background: #fafbfc;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  padding: 16px 20px 20px;
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.12);
  max-height: min(70vh, 480px);
  overflow: auto;
}

.menu-columns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 18px 24px;
}

.menu-group-label {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
}

.menu-items-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.menu-item {
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text);
  text-align: left;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.menu-item:hover:not(.disabled) {
  background: #ecfeff;
  border-color: #99f6e4;
}

.menu-item.active {
  background: #ccfbf1;
  border-color: #2dd4bf;
  color: #115e59;
  font-weight: 600;
}

.menu-item.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.menu-item.placeholder:not(.active) {
  opacity: 0.92;
}

.menu-item-phase {
  font-size: 10px;
  color: #94a3b8;
  font-weight: 500;
}

.menu-drop-enter-active,
.menu-drop-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.menu-drop-enter-from,
.menu-drop-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (max-width: 900px) {
  .topbar-row {
    padding: 8px 12px;
    gap: 10px;
  }

  .brand-sub {
    display: none;
  }

  .menu-trigger span {
    display: none;
  }

  .top-menu-panel {
    padding: 12px;
  }

  .menu-columns {
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .menu-items-row {
    flex-direction: column;
    align-items: stretch;
  }

  .menu-item {
    width: 100%;
    border-radius: 10px;
    white-space: normal;
  }
}
</style>
