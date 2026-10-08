<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

import type { TrafficMinute } from '../../api/system'

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const props = defineProps<{ points: TrafficMinute[] }>()
const container = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | undefined
let resizeObserver: ResizeObserver | undefined

function render() {
  if (!chart) return
  const labels = props.points.map((point) => new Date(point.at).toLocaleTimeString('zh-CN', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  }))
  chart.setOption({
    animation: false,
    color: ['#2563eb', '#dc2626'],
    grid: { left: 44, right: 16, top: 42, bottom: 32 },
    legend: { top: 0, left: 0, textStyle: { color: '#64748b' } },
    tooltip: { trigger: 'axis', confine: true },
    xAxis: { type: 'category', data: labels, axisLabel: { color: '#64748b', interval: 2 }, axisTick: { alignWithLabel: true } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: '#e2e8f0' } } },
    series: [
      { name: '请求数', type: 'bar', data: props.points.map((point) => point.count), barMaxWidth: 22 },
      { name: '5xx', type: 'bar', data: props.points.map((point) => point.error_count), barMaxWidth: 22 },
    ],
  }, { notMerge: true })
}

onMounted(() => {
  if (!container.value) return
  chart = echarts.init(container.value, undefined, { renderer: 'svg' })
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(container.value)
  render()
})

watch(() => props.points, render)

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = undefined
})
</script>

<template>
  <div ref="container" class="traffic-chart" role="img" aria-label="近 15 分钟请求数与 5xx 错误数"></div>
</template>

<style scoped>
.traffic-chart { width: 100%; height: 265px; }
</style>
