<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { getSystemOverview, type SystemOverview } from '../../api/system'
import { formatUserFacingError } from '../../api/client'
import SystemTrafficChart from '../../components/ops/SystemTrafficChart.vue'

const overview = ref<SystemOverview | null>(null)
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(true)
let refreshTimer: ReturnType<typeof setInterval> | undefined

const serviceCards = computed(() => {
  const services = overview.value?.services
  if (!services) return []
  return [
    { name: 'Java BFF', data: services.java_bff },
    { name: 'Python AI', data: services.python_ai },
    { name: 'PostgreSQL', data: services.postgresql },
    { name: 'pgvector', data: services.pgvector },
    { name: 'Redis', data: services.redis },
    { name: 'RabbitMQ', data: services.rabbitmq },
  ]
})

function statusLabel(status: string) {
  if (status === 'ok') return '正常'
  if (status === 'down') return '不可用'
  if (status === 'missing') return '未安装'
  return '未确认'
}

function statusClass(status: string) {
  if (status === 'ok') return 'tag ok'
  if (status === 'down' || status === 'missing') return 'tag fail'
  return 'tag warn'
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatUptime(seconds: number) {
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时 ${Math.floor(seconds % 3600 / 60)} 分钟`
  return `${Math.floor(seconds / 86400)} 天 ${Math.floor(seconds % 86400 / 3600)} 小时`
}

async function refresh() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    overview.value = await getSystemOverview()
  } catch (err) {
    error.value = formatUserFacingError(err)
  } finally {
    loading.value = false
  }
}

function setupAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = autoRefresh.value ? setInterval(refresh, 30_000) : undefined
}

onMounted(() => {
  refresh()
  setupAutoRefresh()
})
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>系统健康</h1>
        <p>入口请求与服务压力 · 统计范围为当前 Java BFF 实例</p>
        <p v-if="overview" class="checked-at">
          采样时间 {{ new Date(overview.checked_at).toLocaleString('zh-CN') }} · 运行 {{ formatUptime(overview.uptime_seconds) }}
        </p>
      </div>
      <div class="actions">
        <label><input v-model="autoRefresh" type="checkbox" @change="setupAutoRefresh" /> 自动刷新</label>
        <button type="button" class="ghost-btn" :disabled="loading" @click="refresh">刷新</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading && !overview" class="hint">加载中…</p>

    <template v-if="overview">
      <div class="stats">
        <article class="stat-card"><span>累计请求</span><strong>{{ overview.requests.total_since_start.toLocaleString() }}</strong><small>BFF 启动以来</small></article>
        <article class="stat-card"><span>近 5 分钟请求</span><strong>{{ overview.requests.last_5m.toLocaleString() }}</strong><small>不含探活与监控轮询</small></article>
        <article class="stat-card"><span>近 5 分钟 5xx</span><strong>{{ overview.requests.errors_5m }}</strong><small>错误率 {{ (overview.requests.error_rate_5m * 100).toFixed(1) }}%</small></article>
        <article class="stat-card"><span>平均响应耗时</span><strong>{{ overview.requests.avg_latency_ms_5m == null ? '—' : `${overview.requests.avg_latency_ms_5m} ms` }}</strong><small>近 5 分钟</small></article>
      </div>

      <section class="panel">
        <h2>近 15 分钟流量</h2>
        <SystemTrafficChart :points="overview.requests.per_minute" />
      </section>

      <div class="grid-2">
        <section class="panel">
          <h2>Java BFF 进程压力</h2>
          <div class="metric-row"><span>当前进行中的请求</span><strong>{{ overview.requests.in_flight }}</strong></div>
          <div class="metric-row"><span>CPU 使用率</span><strong>{{ overview.pressure.cpu_percent == null ? '不可用' : `${overview.pressure.cpu_percent}%` }}</strong></div>
          <div class="metric-row"><span>JVM 堆内存</span><strong>{{ formatBytes(overview.pressure.heap_used_bytes) }} / {{ overview.pressure.heap_max_bytes == null ? '—' : formatBytes(overview.pressure.heap_max_bytes) }}</strong></div>
          <div class="metric-row"><span>堆使用率</span><strong>{{ overview.pressure.heap_usage_percent == null ? '—' : `${overview.pressure.heap_usage_percent}%` }}</strong></div>
          <div class="metric-row"><span>JVM 线程数</span><strong>{{ overview.pressure.thread_count }}</strong></div>
          <div class="metric-row"><span>主机 1 分钟平均负载</span><strong>{{ overview.pressure.load_average_1m ?? '—' }} / {{ overview.pressure.available_processors }} 核</strong></div>
          <p class="hint">CPU 和内存是 Java 进程指标；平均负载来自运行主机，不代表 Python Worker 单独用量。</p>
        </section>

        <section class="panel">
          <h2>依赖连通性</h2>
          <div v-for="svc in serviceCards" :key="svc.name" class="metric-row">
            <span>{{ svc.name }}</span>
            <div class="dependency-status">
              <small v-if="svc.data?.latency_ms != null">{{ svc.data.latency_ms }} ms</small>
              <span :class="statusClass(svc.data?.status ?? 'unknown')">{{ statusLabel(svc.data?.status ?? 'unknown') }}</span>
            </div>
          </div>
          <p v-if="overview.services.redis?.status === 'ok'" class="dependency-detail">
            Redis 内存 {{ overview.services.redis.used_memory_bytes == null ? '—' : formatBytes(overview.services.redis.used_memory_bytes) }}
            · 客户端 {{ overview.services.redis.connected_clients ?? '—' }}
          </p>
          <p v-if="overview.services.rabbitmq?.status === 'ok'" class="dependency-detail">
            ingest 队列：待消费 {{ overview.services.rabbitmq.ready_messages ?? '—' }}
            · 消费者 {{ overview.services.rabbitmq.consumer_count ?? '—' }}
            <span v-if="overview.services.rabbitmq.queue_status !== 'ok'">（队列信息不可用）</span>
            <span v-else-if="overview.services.rabbitmq.consumer_count === 0" class="warning">（当前没有解析 Worker 消费）</span>
          </p>
          <p class="hint">服务状态取自当前探测；Python 不可用时，下游依赖显示“未确认”。</p>
        </section>
      </div>
      <p class="footnote">请求统计保存在当前进程内，服务重启后归零；5xx 错误率不包含业务性 4xx。</p>
    </template>
  </section>
</template>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; }
.head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; flex-wrap: wrap; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.head p { margin: 0; color: var(--text-muted); font-size: 13px; }
.head .checked-at { margin-top: 6px; font-size: 12px; }
.actions { display: flex; align-items: center; gap: 14px; font-size: 13px; color: var(--text-muted); }
.actions label { display: flex; align-items: center; gap: 6px; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat-card, .panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
.stat-card { display: flex; flex-direction: column; gap: 8px; }
.stat-card span, .stat-card small, .hint, .footnote { color: var(--text-muted); font-size: 13px; }
.stat-card strong { font-size: 25px; color: var(--text-strong); font-weight: 650; }
.panel { margin-bottom: 16px; }
.panel h2 { margin: 0 0 12px; font-size: 16px; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.metric-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.metric-row strong { font-weight: 600; }
.dependency-status { display: flex; align-items: center; gap: 8px; }
.dependency-status small { color: var(--text-muted); }
.dependency-detail { margin: 8px 0 0; font-size: 12px; color: var(--text-muted); }
.warning { color: #b45309; font-weight: 600; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.tag.ok { background: #ecfdf5; color: #047857; }
.tag.fail { background: #fef2f2; color: #b91c1c; }
.tag.warn { background: #fff7ed; color: #c2410c; }
.hint { margin: 12px 0 0; }
.footnote { margin: 0 0 20px; }
.error { color: #b91c1c; }
@media (max-width: 900px) { .stats { grid-template-columns: repeat(2, 1fr); } .grid-2 { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .stats { grid-template-columns: 1fr; } }
</style>
