<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { IngestBatchEvent } from '../../api/ops'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const props = defineProps<{ events: IngestBatchEvent[]; total: number; live?: boolean }>()
const container = ref<HTMLElement | null>(null)
const intervalMinutes = ref(5)
let chart: ReturnType<typeof echarts.init> | undefined
let resizeObserver: ResizeObserver | undefined

const intervalOptions = [1, 5, 10, 15, 30, 60]
const tickTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  hour: '2-digit', minute: '2-digit', hour12: false,
})
const tooltipTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
})

const series = [
  { key: 'pending', name: '待处理', color: '#94a3b8' },
  { key: 'active', name: '处理中', color: '#2563eb' },
  { key: 'done', name: '完成', color: '#059669' },
  { key: 'failed', name: '失败', color: '#dc2626' },
] as const

function renderChart() {
  if (!chart) return
  const now = Date.now()
  const history = props.events.length ? props.events : [{
    at: new Date(now).toISOString(), pending: props.total, active: 0, done: 0, failed: 0,
  }]
  const points = props.live ? [...history, { ...history[history.length - 1]!, at: new Date(now).toISOString() }] : history
  const first = Date.parse(points[0]!.at)
  const last = Date.parse(points[points.length - 1]!.at)
  const intervalMs = intervalMinutes.value * 60_000
  const axisMin = Math.floor(first / intervalMs) * intervalMs
  const axisMax = Math.max(axisMin + intervalMs, Math.ceil(last / intervalMs) * intervalMs)
  chart.setOption({
    animation: false,
    color: series.map((item) => item.color),
    grid: { left: 38, right: 16, top: 42, bottom: 42 },
    legend: { top: 0, left: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: '#64748b' } },
    tooltip: {
      trigger: 'axis', confine: true, axisPointer: { type: 'line' },
      formatter: (params: unknown) => {
        const rows = (Array.isArray(params) ? params : [params]) as Array<{
          seriesName: string; value: [number, number]
        }>
        if (!rows.length) return ''
        return [
          tooltipTimeFormatter.format(rows[0]!.value[0]),
          ...rows.map((row) => `${row.seriesName}：${row.value[1]} 份`),
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'value', min: axisMin, max: axisMax, interval: intervalMs,
      axisLabel: {
        formatter: (value: number) => tickTimeFormatter.format(value),
        color: '#64748b', hideOverlap: true,
      },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value', min: 0, max: Math.max(1, props.total), minInterval: 1,
      axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: '#e2e8f0' } },
    },
    series: series.map((item) => ({
      name: item.name, type: 'line' as const, step: 'end' as const,
      showSymbol: points.length <= 2, symbolSize: 6,
      data: points.map((event) => [Date.parse(event.at), event[item.key]]),
    })),
  }, { notMerge: true })
}

onMounted(() => {
  if (!container.value) return
  chart = echarts.init(container.value, undefined, { renderer: 'svg' })
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(container.value)
  renderChart()
})
watch(() => [props.events, props.total, props.live, intervalMinutes.value], renderChart)
onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = undefined
})
</script>

<template>
  <div class="chart-wrap">
    <label class="interval-control">
      横轴间隔
      <select v-model.number="intervalMinutes" aria-label="横轴间隔分钟数">
        <option v-for="minutes in intervalOptions" :key="minutes" :value="minutes">{{ minutes }} 分钟</option>
      </select>
    </label>
    <div ref="container" class="chart" role="img" :aria-label="`解析任务文件数变化，共 ${total} 份；横轴间隔 ${intervalMinutes} 分钟`" />
  </div>
</template>

<style scoped>
.chart-wrap { min-width: 0; }
.interval-control { display: flex; align-items: center; gap: 8px; color: #64748b; font-size: 12px; }
.interval-control select { border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; color: #334155; padding: 3px 6px; }
.chart { width: 100%; height: 240px; min-width: 0; }
</style>
