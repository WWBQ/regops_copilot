<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { documentViewerPage } from '../../api/documents'
import {
  METRIC_STATUS_LABELS,
  STATEMENT_LABELS,
  listFinMetrics,
  type FinMetricItem,
} from '../../api/quality'
import DocumentPdfFrame from '../../components/documents/DocumentPdfFrame.vue'
import type { Citation } from '../../types/chat'

const props = defineProps<{
  citation: Citation
}>()

defineEmits<{
  close: []
}>()

const factItems = ref<FinMetricItem[]>([])
const factLoading = ref(false)
const factError = ref('')
let factRequestId = 0

// 兼容合规问答保存的旧 Citation：旧记录没有 kind，只通过 doc_id / href 区分来源。
const isFacts = computed(() => (
  props.citation.kind === 'facts'
  || Boolean(props.citation.href?.startsWith('/quality/facts'))
))
const isDocument = computed(() => (
  props.citation.kind === 'document'
  || (!isFacts.value && props.citation.kind !== 'web' && Boolean(props.citation.doc_id))
))

function hrefFilters(): { companyCode: string; concept: string } {
  if (!props.citation.href) return { companyCode: '', concept: '' }
  try {
    const url = new URL(props.citation.href, window.location.origin)
    return {
      companyCode: url.searchParams.get('company_code') ?? '',
      concept: url.searchParams.get('concept') ?? '',
    }
  } catch {
    return { companyCode: '', concept: '' }
  }
}

const companyCode = computed(() => props.citation.company_code || hrefFilters().companyCode)
const concept = computed(() => props.citation.concept || hrefFilters().concept)
const citationYear = computed(() => {
  if (props.citation.year) return props.citation.year
  const match = `${props.citation.title ?? ''} ${props.citation.snippet}`.match(/\b(20\d{2})\b/)
  return match ? Number(match[1]) : null
})

const fullPageHref = computed(() => {
  if (isDocument.value) {
    return documentViewerPage(props.citation.doc_id, props.citation.page)
  }
  return props.citation.href || '/quality/facts'
})

async function loadFacts() {
  if (!isFacts.value) {
    factItems.value = []
    factError.value = ''
    return
  }
  const requestId = ++factRequestId
  factLoading.value = true
  factError.value = ''
  try {
    const response = await listFinMetrics({
      limit: 100,
      company_code: companyCode.value || undefined,
      concept: concept.value || undefined,
    })
    if (requestId === factRequestId) factItems.value = response.items
  } catch (cause) {
    if (requestId === factRequestId) {
      factItems.value = []
      factError.value = cause instanceof Error ? cause.message : '财务事实加载失败'
    }
  } finally {
    if (requestId === factRequestId) factLoading.value = false
  }
}

function isCitedPeriod(row: FinMetricItem): boolean {
  return citationYear.value != null && row.period.startsWith(String(citationYear.value))
}

function statusClass(status: string): string {
  if (status === 'auto_accepted') return 'ok'
  if (status === 'human_review') return 'warn'
  return 'fail'
}

watch(() => props.citation, () => { void loadFacts() }, { immediate: true })
</script>

<template>
  <aside class="risk-evidence-panel" aria-label="引用证据">
    <header class="evidence-header">
      <div class="evidence-heading">
        <span class="evidence-kind">{{ isDocument ? '年报证据' : isFacts ? '财务事实' : '引用来源' }}</span>
        <h2>{{ citation.title || citation.doc_id }}</h2>
        <p v-if="isDocument">第 {{ citation.page }} 页</p>
        <p v-else-if="companyCode || concept">
          {{ companyCode }}<template v-if="companyCode && concept"> · </template>{{ concept }}
        </p>
      </div>
      <button type="button" class="evidence-close" aria-label="关闭证据面板" @click="$emit('close')">×</button>
    </header>

    <div class="evidence-toolbar">
      <a :href="fullPageHref" target="_blank" rel="noopener noreferrer">在完整页面打开 ↗</a>
    </div>

    <p v-if="citation.snippet" class="evidence-snippet">{{ citation.snippet }}</p>

    <div v-if="isDocument" class="evidence-document">
      <DocumentPdfFrame :doc-id="citation.doc_id" :page="citation.page" />
    </div>

    <div v-else-if="isFacts" class="evidence-facts">
      <p v-if="factLoading" class="evidence-state">正在加载财务事实…</p>
      <p v-else-if="factError" class="evidence-state error">{{ factError }}</p>
      <p v-else-if="!factItems.length" class="evidence-state">没有找到对应的财务事实记录。</p>
      <div v-else class="fact-list">
        <article
          v-for="row in factItems"
          :key="row.id"
          class="fact-card"
          :class="{ cited: isCitedPeriod(row) }"
        >
          <header>
            <div>
              <strong>{{ row.period }}</strong>
              <span v-if="isCitedPeriod(row)" class="cited-label">本次引用</span>
            </div>
            <span class="fact-status" :class="statusClass(row.status)">
              {{ METRIC_STATUS_LABELS[row.status] ?? row.status }}
            </span>
          </header>
          <p class="fact-value">{{ row.value_display ?? row.value_yuan ?? '—' }}</p>
          <dl>
            <div><dt>公司</dt><dd>{{ row.company_name ?? row.company_code ?? '—' }}</dd></div>
            <div><dt>科目</dt><dd>{{ row.raw_name ?? row.concept }}</dd></div>
            <div><dt>报表</dt><dd>{{ STATEMENT_LABELS[row.statement] ?? row.statement }}</dd></div>
            <div><dt>原始值</dt><dd>{{ row.raw_value ?? '—' }} {{ row.unit_raw ?? '' }}</dd></div>
            <div><dt>文档</dt><dd class="mono">{{ row.doc_id || '—' }}</dd></div>
            <div><dt>页码</dt><dd>{{ row.page_no ?? '—' }}</dd></div>
          </dl>
          <p v-if="row.review_reason" class="fact-review">{{ row.review_reason }}</p>
        </article>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.risk-evidence-panel {
  flex: 0 0 min(48%, 760px);
  min-width: 440px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #fff;
  box-shadow: var(--shadow);
}

.evidence-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border);
}

.evidence-heading { min-width: 0; }
.evidence-kind {
  display: inline-flex;
  margin-bottom: 5px;
  padding: 2px 8px;
  border-radius: 999px;
  color: #0f766e;
  background: #ccfbf1;
  font-size: 12px;
  font-weight: 700;
}
.evidence-heading h2 {
  margin: 0;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 16px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-heading p { margin: 3px 0 0; color: var(--muted); font-size: 12px; }
.evidence-close {
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 8px;
  color: var(--muted);
  background: #f1f5f9;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}
.evidence-close:hover { color: var(--text-strong); background: #e2e8f0; }

.evidence-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: #f8fafc;
}
.evidence-toolbar a { color: #0f766e; font-size: 12px; font-weight: 600; text-decoration: none; }
.evidence-toolbar a:hover { text-decoration: underline; }

.evidence-snippet {
  flex: 0 0 auto;
  max-height: 112px;
  margin: 0;
  padding: 10px 16px;
  overflow: auto;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  background: #f8fafc;
  font-size: 13px;
}

.evidence-document { flex: 1; min-height: 0; padding: 10px; }
.evidence-facts { flex: 1; min-height: 0; overflow: auto; padding: 12px; background: #f8fafc; }
.evidence-state { margin: 32px 0; text-align: center; color: var(--muted); }
.evidence-state.error { color: #991b1b; }
.fact-list { display: grid; gap: 10px; }
.fact-card { padding: 12px; border: 1px solid var(--border); border-radius: 12px; background: #fff; }
.fact-card.cited { border-color: #14b8a6; box-shadow: 0 0 0 2px rgba(20, 184, 166, 0.1); }
.fact-card header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.fact-card header strong { color: var(--text-strong); }
.cited-label { margin-left: 8px; color: #0f766e; font-size: 11px; font-weight: 700; }
.fact-status { padding: 2px 7px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.fact-status.ok { color: #166534; background: #dcfce7; }
.fact-status.warn { color: #92400e; background: #fef3c7; }
.fact-status.fail { color: #991b1b; background: #fee2e2; }
.fact-value { margin: 8px 0; color: #0f766e; font-size: 19px; font-weight: 700; }
.fact-card dl { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; margin: 0; font-size: 12px; }
.fact-card dl div { min-width: 0; }
.fact-card dt { color: var(--muted); }
.fact-card dd { margin: 1px 0 0; overflow-wrap: anywhere; color: var(--text); }
.fact-review { margin: 9px 0 0; padding-top: 8px; border-top: 1px dashed var(--border); color: #92400e; font-size: 12px; }
.mono { font-family: var(--mono); }

@media (max-width: 1050px) {
  .risk-evidence-panel { min-width: 380px; flex-basis: 48%; }
}
</style>
