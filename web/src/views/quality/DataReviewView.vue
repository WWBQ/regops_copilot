<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuth } from '../../composables/useAuth'
import { documentViewerPage } from '../../api/documents'
import {
  getReviewDetail,
  listReviewQueue,
  submitReview,
  METRIC_STATUS_LABELS,
  type ReviewDetail,
  type ReviewQueueItem,
} from '../../api/quality'

const route = useRoute()
const router = useRouter()
const auth = useAuth()
const view = computed<'pending' | 'reviewed'>(() => route.path.endsWith('/completed') ? 'reviewed' : 'pending')
const canReview = computed(() => auth.user.value?.role !== 'RM')

const items = ref<ReviewQueueItem[]>([])
const total = ref(0)
const offset = ref(0)
const queueLoading = ref(false)
const queueError = ref('')
const detail = ref<ReviewDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const saveError = ref('')
const notice = ref('')
const saving = ref(false)
const decision = ref<'approve' | 'reject'>('approve')
const amount = ref('')
const note = ref('')
const confirmed = ref(false)

const selectedId = computed(() => {
  const value = Number(route.query.fact_id)
  return Number.isSafeInteger(value) && value > 0 ? value : null
})

async function loadQueue(append = false) {
  queueLoading.value = true
  queueError.value = ''
  try {
    const response = await listReviewQueue(view.value, append ? offset.value : 0)
    items.value = append ? [...items.value, ...response.items] : response.items
    total.value = response.total
    offset.value = items.value.length
    if (!selectedId.value && items.value.length) {
      void router.replace({ path: route.path, query: { fact_id: String(items.value[0].id) } })
    }
  } catch (cause) {
    queueError.value = cause instanceof Error ? cause.message : '审核队列加载失败'
  } finally {
    queueLoading.value = false
  }
}

async function loadDetail(metricId: number | null) {
  detail.value = null
  detailError.value = ''
  saveError.value = ''
  notice.value = ''
  if (!metricId) return
  detailLoading.value = true
  try {
    const response = await getReviewDetail(metricId)
    detail.value = response
    amount.value = response.valueYuan ?? ''
    note.value = ''
    decision.value = 'approve'
    confirmed.value = false
  } catch (cause) {
    detailError.value = cause instanceof Error ? cause.message : '审核详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function selectItem(item: ReviewQueueItem) {
  void router.replace({ path: route.path, query: { fact_id: String(item.id) } })
}

async function saveReview() {
  const fact = detail.value
  if (!fact || fact.status !== 'human_review' || saving.value) return
  saveError.value = ''
  if (!confirmed.value) {
    saveError.value = '请先确认已核对原始数据与来源'
    return
  }
  if (note.value.trim().length < 10) {
    saveError.value = '请填写至少 10 字的核对依据'
    return
  }
  if (decision.value === 'approve' && !/^-?\d{1,20}(?:\.\d{1,4})?$/.test(amount.value.trim())) {
    saveError.value = '修订金额须为元，最多 4 位小数'
    return
  }
  saving.value = true
  try {
    detail.value = await submitReview(fact.metricId, {
      decision: decision.value,
      reviewedValueYuan: decision.value === 'approve' ? amount.value.trim() : null,
      note: note.value.trim(),
      expectedUpdatedAt: fact.updatedAt,
    })
    notice.value = decision.value === 'approve' ? '已人工确认，审核记录已保存' : '已拒绝，审核记录已保存'
    await loadQueue()
  } catch (cause) {
    saveError.value = cause instanceof Error ? cause.message : '保存审核失败'
  } finally {
    saving.value = false
  }
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

watch(() => route.path, () => {
  items.value = []
  total.value = 0
  offset.value = 0
  void loadQueue()
}, { immediate: true })
watch(selectedId, (id) => { void loadDetail(id) }, { immediate: true })
</script>

<template>
  <section class="review-page">
    <header class="head">
      <div>
        <h1>数据审核</h1>
        <p>质量门未通过的财务事实进入待审核队列。原始值只读；审核决定、修订金额和核对依据均留痕。</p>
      </div>
      <button type="button" class="ghost-btn" :disabled="queueLoading" @click="loadQueue()">刷新</button>
    </header>

    <div class="review-grid">
      <section class="queue-panel" aria-label="审核列表">
        <div class="panel-head">
          <strong>{{ view === 'pending' ? '待审核' : '已审核' }}</strong>
          <span>{{ total }} 条</span>
        </div>
        <p v-if="queueError" class="error">{{ queueError }}</p>
        <p v-if="queueLoading && !items.length" class="empty">加载中…</p>
        <p v-else-if="!items.length" class="empty">{{ view === 'pending' ? '暂无待审核事实' : '暂无审核记录' }}</p>
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          class="queue-item"
          :class="{ active: selectedId === item.id }"
          @click="selectItem(item)"
        >
          <strong>{{ item.companyCode }} · {{ item.concept }}</strong>
          <span>{{ item.period }} · {{ item.valueYuan ?? '无金额' }} 元</span>
          <small>{{ METRIC_STATUS_LABELS[item.status] ?? item.status }} · {{ item.reviewReason ?? '—' }}</small>
        </button>
        <button v-if="items.length < total" type="button" class="load-more" :disabled="queueLoading" @click="loadQueue(true)">加载更多</button>
      </section>

      <section class="detail-panel" aria-label="审核详情">
        <p v-if="detailLoading" class="empty">正在读取事实…</p>
        <p v-else-if="detailError" class="error empty">{{ detailError }}</p>
        <p v-else-if="!detail" class="empty">从左侧选择一条财务事实</p>
        <template v-else>
          <div class="detail-head">
            <div>
              <h2>{{ detail.companyCode }} · {{ detail.concept }}</h2>
              <p>{{ detail.period }} · {{ detail.docId }} · {{ METRIC_STATUS_LABELS[detail.status] ?? detail.status }}</p>
            </div>
            <router-link :to="{ path: '/quality/facts', query: { company_code: detail.companyCode, concept: detail.concept } }">返回事实库</router-link>
          </div>

          <div class="facts">
            <div><span>当前金额</span><strong>{{ detail.valueYuan ?? '—' }} 元</strong></div>
            <div><span>原始文本</span><strong>{{ detail.rawValue ?? '—' }}</strong></div>
            <div><span>质量门原因</span><strong>{{ (detail.status === 'human_review' ? detail.reviewReason : detail.history[0]?.originalReason) ?? '—' }}</strong></div>
            <div><span>来源</span><strong>{{ detail.sourceType }} · {{ detail.pageNo ? `第 ${detail.pageNo} 页` : '无页码' }}</strong></div>
            <div><span>原始字段</span><strong>{{ detail.xbrlTag ?? detail.rawName ?? '—' }} · {{ detail.unitRaw ?? '单位未知' }}</strong></div>
            <div><span>报表 / 口径</span><strong>{{ detail.statement }} · {{ detail.scope }}</strong></div>
            <div class="wide"><span>来源哈希</span><code>{{ detail.contentHash ?? '无' }}</code></div>
          </div>
          <p v-if="detail.sourceType === 'pdf'" class="source-link">
            <a :href="documentViewerPage(detail.docId, detail.pageNo ?? undefined)" target="_blank" rel="noopener noreferrer">打开 PDF 原页核对</a>
          </p>

          <form v-if="detail.status === 'human_review' && canReview" class="review-form" @submit.prevent="saveReview">
            <h3>审核决定</h3>
            <div class="choice-row">
              <label><input v-model="decision" type="radio" value="approve" /> 确认通过</label>
              <label><input v-model="decision" type="radio" value="reject" /> 拒绝使用</label>
            </div>
            <label v-if="decision === 'approve'" class="field">
              修订金额（元）
              <input v-model="amount" inputmode="decimal" type="text" placeholder="请输入核对后的金额" />
            </label>
            <label class="field">
              核对依据与处理说明
              <textarea v-model="note" rows="4" maxlength="1000" placeholder="说明核对了哪些原始数据、为何确认或拒绝（至少 10 字）" />
            </label>
            <label class="confirm"><input v-model="confirmed" type="checkbox" /> 我已核对原始数据及来源信息</label>
            <p class="hint">确认通过后才会进入受控问数；拒绝后不会被使用。所有操作保留原值和审核记录。</p>
            <p v-if="saveError" class="error">{{ saveError }}</p>
            <button type="submit" class="primary-btn" :disabled="saving">{{ saving ? '保存中…' : '提交审核' }}</button>
          </form>
          <p v-else-if="detail.status === 'human_review'" class="hint">当前角色只能查看，不能提交审核。</p>
          <p v-if="notice" class="success" role="status">{{ notice }}</p>

          <section class="history">
            <h3>审核记录</h3>
            <p v-if="!detail.history.length" class="hint">暂无审核记录</p>
            <article v-for="entry in detail.history" :key="entry.id" class="history-item">
              <strong>{{ entry.decision === 'approve' ? '确认通过' : '拒绝使用' }}</strong>
              <span>{{ entry.reviewerName }} · {{ formatTime(entry.createdAt) }}</span>
              <p>原金额 {{ entry.originalValueYuan ?? '—' }} 元 → {{ entry.reviewedValueYuan ?? '拒绝使用' }}{{ entry.reviewedValueYuan ? ' 元' : '' }}</p>
              <p>{{ entry.note }}</p>
              <small>原状态：{{ METRIC_STATUS_LABELS[entry.originalStatus] ?? entry.originalStatus }} · 原原因：{{ entry.originalReason ?? '—' }}</small>
            </article>
          </section>
        </template>
      </section>
    </div>
  </section>
</template>

<style scoped>
.review-page { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.head, .detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.head h1 { margin: 0 0 6px; font-size: 24px; }
.head p, .detail-head p { margin: 0; color: var(--text-muted); font-size: 13px; }
.ghost-btn, .load-more { padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); cursor: pointer; }
.review-grid { display: grid; grid-template-columns: minmax(280px, 340px) minmax(0, 1fr); gap: 14px; min-height: 550px; }
.queue-panel, .detail-panel { min-width: 0; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.queue-panel { overflow: auto; max-height: calc(100vh - 185px); }
.detail-panel { padding: 18px; }
.panel-head { display: flex; justify-content: space-between; padding: 16px; border-bottom: 1px solid var(--border); }
.panel-head span, .queue-item span, .queue-item small, .history-item span, .history-item small { color: var(--text-muted); font-size: 12px; }
.queue-item { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; width: 100%; padding: 14px 16px; text-align: left; border: 0; border-bottom: 1px solid var(--border); background: transparent; cursor: pointer; }
.queue-item:hover, .queue-item.active { background: #edf7f5; }
.queue-item.active { box-shadow: inset 3px 0 #0f766e; }
.queue-item small { max-width: 100%; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.load-more { margin: 12px; }
.detail-head h2 { margin: 0 0 5px; font-size: 18px; }
.detail-head a, .source-link a { color: #0f766e; font-size: 13px; }
.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }
.facts > div { display: flex; flex-direction: column; gap: 5px; min-width: 0; padding: 12px; background: #f8fafc; border-radius: 8px; }
.facts span { font-size: 12px; color: var(--text-muted); }
.facts strong { overflow-wrap: anywhere; font-size: 13px; }
.facts .wide { grid-column: 1 / -1; }
.facts code { overflow-wrap: anywhere; font-size: 12px; }
.review-form, .history { margin-top: 22px; border-top: 1px solid var(--border); padding-top: 16px; }
.review-form h3, .history h3 { margin: 0 0 12px; font-size: 16px; }
.choice-row { display: flex; gap: 20px; margin-bottom: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; font-size: 13px; font-weight: 600; }
.field input, .field textarea { width: 100%; padding: 9px 11px; border: 1px solid var(--border); border-radius: 8px; font: inherit; font-weight: 400; }
.confirm { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.primary-btn { padding: 9px 18px; border: 0; border-radius: 8px; background: #0f766e; color: #fff; cursor: pointer; }
.primary-btn:disabled { opacity: .6; cursor: wait; }
.history-item { padding: 12px 0; border-bottom: 1px solid var(--border); }
.history-item span { margin-left: 10px; }
.history-item p { margin: 6px 0; font-size: 13px; overflow-wrap: anywhere; }
.hint, .empty { color: var(--text-muted); font-size: 13px; }
.empty { padding: 24px; text-align: center; }
.error { color: #b91c1c; font-size: 13px; }
.success { color: #047857; font-size: 13px; }
@media (max-width: 960px) { .review-grid { grid-template-columns: 1fr; } .queue-panel { max-height: 300px; } }
</style>
