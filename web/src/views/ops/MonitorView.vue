<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AgentMonitorView from './AgentMonitorView.vue'
import AsknumMonitorView from './AsknumMonitorView.vue'
import RagMonitorView from './RagMonitorView.vue'

const route = useRoute()
const currentView = computed(() => {
  if (route.path.endsWith('/agent')) return AgentMonitorView
  if (route.path.endsWith('/asknum')) return AsknumMonitorView
  return RagMonitorView
})
</script>

<template>
  <component :is="currentView" :key="route.path" />
</template>
