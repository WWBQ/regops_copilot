<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { listAnnualReports, type AnnualReport } from '../../api/annualReports'

const reports = ref<AnnualReport[]>([])
const loading = ref(true)
const error = ref('')
const keyword = ref('')
const year = ref('')
const copiedId = ref('')

const companyNames: Record<string, string> = {
  '000333': '美的集团',
  '000651': '格力电器',
  '002594': '比亚迪',
  '300750': '宁德时代',
  '600031': '三一重工',
  '600519': '贵州茅台',
  '601633': '长城汽车',
}

const years = computed(() => [...new Set(reports.value.map((item) => item.report_year))].sort((a, b) => b - a))
const filteredReports = computed(() => reports.value.filter((item) => {
  const needle = keyword.value.trim().toLowerCase()
  if (year.value && item.report_year !== Number(year.value)) return false
  return !needle || [item.doc_id, item.company_code, item.source_filename, companyNames[item.company_code] ?? '']
    .some((value) => value.toLowerCase().includes(needle))
}))

async function refresh() {
  loading.value = true
  error.value = ''
  copiedId.value = ''
  try {
    reports.value = (await listAnnualReports()).items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '年报列表加载失败'
  } finally {
    loading.value = false
  }
}

function formatSize(size: number) {
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN')
}

async function copyObjectUrl(item: AnnualReport) {
  if (!item.object_url) return
  try {
    await navigator.clipboard.writeText(item.object_url)
    copiedId.value = item.doc_id
  } catch {
    error.value = '复制失败，请手动选中链接复制'
  }
}

onMounted(refresh)
</script>

<template>
  <section class="reports-page">
    <header class="head">
      <div>
        <h1>PDF 年报</h1>
        <p>已登记的公开年报目录。对象存储链接是短期签名 URL，刷新列表后重新生成，有效期 5 分钟。</p>
      </div>
      <button type="button" class="ghost-btn" :disabled="loading" @click="refresh">刷新</button>
    </header>

    <div class="filters">
      <input v-model="keyword" type="search" placeholder="搜索公司、证券代码或文件名" aria-label="搜索年报" />
      <select v-model="year" aria-label="筛选年份">
        <option value="">全部年份</option>
        <option v-for="item in years" :key="item" :value="String(item)">{{ item }} 年</option>
      </select>
      <span class="count">{{ filteredReports.length }} 份年报</span>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="table-wrap">
      <table class="report-table">
        <thead>
          <tr>
            <th>公司</th>
            <th>年份</th>
            <th>文档 ID</th>
            <th>文件名</th>
            <th>页数</th>
            <th>大小</th>
            <th>状态</th>
            <th>对象存储 URL</th>
            <th>更新时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filteredReports" :key="item.doc_id">
            <td>{{ companyNames[item.company_code] ?? item.company_code }} <span class="muted">{{ item.company_code }}</span></td>
            <td>{{ item.report_year }}</td>
            <td class="mono">{{ item.doc_id }}</td>
            <td>{{ item.source_filename }}</td>
            <td>{{ item.page_count ?? '—' }}</td>
            <td>{{ formatSize(item.size) }}</td>
            <td>{{ item.ingest_status === 'ready' ? '已解析' : 'PDF 已登记' }}</td>
            <td class="url-cell">
              <template v-if="item.object_url">
                <code class="object-url" :title="item.object_url">{{ item.object_url }}</code>
                <button type="button" class="copy-btn" :aria-label="`复制 ${item.doc_id} 的对象存储 URL`" @click="copyObjectUrl(item)">
                  {{ copiedId === item.doc_id ? '已复制' : '复制' }}
                </button>
              </template>
              <span v-else class="muted">源文件不可用</span>
            </td>
            <td>{{ formatTime(item.updated_at) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="loading" class="empty">正在加载年报…</p>
      <p v-else-if="!filteredReports.length" class="empty">{{ reports.length ? '没有符合条件的年报' : '暂无已登记的年报 PDF' }}</p>
    </div>
  </section>
</template>

<style scoped>
.reports-page { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.head p { margin: 0; color: var(--text-muted); font-size: 13px; }
.ghost-btn { padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); cursor: pointer; }
.ghost-btn:disabled { cursor: wait; opacity: .6; }
.filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filters input, .filters select { padding: 9px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); font: inherit; }
.filters input { width: min(360px, 100%); }
.count { color: var(--text-muted); font-size: 13px; }
.error { color: #b91c1c; margin: 0; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.report-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
.report-table th, .report-table td { padding: 12px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.report-table th { background: #f8fafc; color: var(--text-muted); font-weight: 600; }
.report-table tbody tr:last-child td { border-bottom: 0; }
.report-table tbody tr:hover { background: #f8fafc; }
.url-cell { min-width: 260px; max-width: 380px; }
.object-url { display: inline-block; vertical-align: middle; max-width: min(280px, 30vw); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.copy-btn { margin-left: 8px; padding: 4px 7px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: #0f766e; cursor: pointer; font-size: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.muted { color: var(--text-muted); margin-left: 5px; }
.empty { padding: 28px; margin: 0; color: var(--text-muted); text-align: center; }
</style>
