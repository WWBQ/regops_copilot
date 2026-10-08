<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from './components/layout/AppShell.vue'
import { SERVICE_HEALTH_KEY, createServiceHealth } from './composables/useServiceHealth'

const health = createServiceHealth()
provide(SERVICE_HEALTH_KEY, health)
const route = useRoute()

const backendOk = computed(() => health.javaOk.value)

function onConnected(model: string) {
  health.javaOk.value = true
  health.pythonOk.value = true
  health.pythonError.value = null
  health.modelName.value = model
}

function onDisconnected() {
  health.pythonOk.value = false
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  void health.refresh()
  pollTimer = setInterval(() => void health.refresh(), 20000)
})

onBeforeUnmount(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
})
</script>

<template>
  <AppShell v-if="route.path !== '/login'">
    <router-view v-slot="{ Component }">
      <component
        :is="Component"
        :backend-ok="backendOk"
        :model-name="health.modelName.value"
        @connected="onConnected"
        @disconnected="onDisconnected"
        @refresh="health.refresh"
      />
    </router-view>
  </AppShell>
  <router-view v-else />
</template>
