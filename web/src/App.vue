<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { getHealth, getModels } from './api/chat'
import AppShell from './components/layout/AppShell.vue'

const backendOk = ref<boolean | null>(null)
const modelName = ref<string | null>(null)

async function refreshStatus() {
  try {
    const [health, models] = await Promise.all([getHealth(), getModels()])
    backendOk.value = health.status === 'ok'
    modelName.value = models.available[0] ?? null
  } catch {
    backendOk.value = false
    modelName.value = null
  }
}

function onConnected(model: string) {
  backendOk.value = true
  modelName.value = model
}

function onDisconnected() {
  backendOk.value = false
}

onMounted(refreshStatus)
</script>

<template>
  <AppShell>
    <router-view v-slot="{ Component }">
      <component
        :is="Component"
        :backend-ok="backendOk"
        :model-name="modelName"
        @connected="onConnected"
        @disconnected="onDisconnected"
        @refresh="refreshStatus"
      />
    </router-view>
  </AppShell>
</template>
