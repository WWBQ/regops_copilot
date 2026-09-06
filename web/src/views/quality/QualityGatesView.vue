<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  fetchQualityGates,
  ingestFinMetrics,
  type QualityCompanyGate,
  type QualityGatesResponse,
} from '../../api/quality'

const router = useRouter()
const data = ref<QualityGatesResponse | null>(null)
const loading = ref(true)
const ingesting = ref(false)
const error = ref('')
const ingestHint = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchQualityGates()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function ingest() {
  ingesting.value = true
  ingestHint.value = ''
  error.value = ''
  try {
    const result = await ingestFinMetrics({ year: 2024 })
    ingestHint.value = `已写入 ${result.summary.facts} 条事实 / ${result.summary.companies} 家公司`
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '入库失败'
  } finally {
    ingesting.value = false
  }
}

function passClass(passed: boolean) {
  return passed ? 'tag ok' : 'tag fail'
}

function goFacts(row: QualityCompanyGate) {
  router.push({ path: '/quality/facts', query: { company_code: row.company_code } })
}

const summary = computed(() => data.value?.summary)

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>质量门 G1 / G2 / G3</h1>
        <p>
          F10 结构化三表写入 <code>fin_metric</code> 前过三道门：金额一致性、财务勾稽（R01–R03）、证据溯源。
          冲突进人工复核，不静默挑数。当前数字源是东方财富 F10 JSON，G3 用 content_hash 而非 PDF bbox。
        </p>
      </div>
      <div class="actions">
        <button type="button" class="ghost-btn" @click="refresh">刷新</button>
        <button type="button" class="primary-btn" :disabled="ingesting" @click="ingest">
          {{ ingesting ? '入库中…' : '从 F10 入库' }}
        </button>
      </div>
    </header>

    <nav class="quick-links">
      <router-link to="/quality/facts" class="quick-link">财务事实库</router-link>
      <router-link to="/ops/ingest" class="quick-link">解析监控</router-link>
    </nav>

    <p v-if="loading && !data" class="hint">加载中…</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="ingestHint" class="ok">{{ ingestHint }}</p>

    <template v-if="summary">
      <div class="stats">
        <article class="stat-card">
          <p class="stat-label">公司</p>
          <p class="stat-value">{{ summary.companies }}</p>
          <p class="stat-sub">{{ summary.facts }} 条事实</p>
        </article>
        <article class="stat-card">
          <p class="stat-label">自动通过</p>
          <p class="stat-value">{{ summary.auto_accepted }}</p>
          <p class="stat-sub">人工复核 {{ summary.human_review }}</p>
        </article>
        <article class="stat-card">
          <p class="stat-label">G2 勾稽</p>
          <p class="stat-value">{{ summary.g2_all_passed ? '全部通过' : '有复核' }}</p>
          <p class="stat-sub">R01 资产负债表 · R02 现金 · R03 净利润</p>
        </article>
        <article class="stat-card">
          <p class="stat-label">G3 溯源</p>
          <p class="stat-value">{{ summary.g3_all_passed ? '齐全' : '缺证据' }}</p>
          <p class="stat-sub">F10 使用 JSON content_hash</p>
        </article>
      </div>

      <p v-if="data && !data.companies.length" class="hint">
        还没有 fin_metric。请先运行
        <code>python python-ai/scripts/download_xbrl.py</code>
        再点「从 F10 入库」，或
        <code>python python-ai/scripts/ingest_fin_metric.py</code>。
      </p>

      <section v-if="data?.companies.length" class="panel">
        <h2>金样本公司</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>公司</th>
                <th>期间</th>
                <th>G1</th>
                <th>R01</th>
                <th>R02</th>
                <th>R03</th>
                <th>G3</th>
                <th>状态</th>
                <th>缺科目</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in data.companies"
                :key="row.doc_id"
                class="clickable"
                @click="goFacts(row)"
              >
                <td>{{ row.company_name }} <span class="mono">{{ row.company_code }}</span></td>
                <td>{{ row.period }}</td>
                <td><span :class="passClass(row.g1.passed)">{{ row.g1.passed ? '通过' : '冲突' }}</span></td>
                <td v-for="rule in row.g2.rules" :key="rule.rule_id">
                  <span :class="passClass(rule.passed)" :title="rule.message">
                    {{ rule.passed ? '通过' : '失败' }}
                  </span>
                </td>
                <td><span :class="passClass(row.g3.passed)">{{ row.g3.passed ? '通过' : '缺证据' }}</span></td>
                <td>{{ row.auto_accepted }}/{{ row.fact_count }} 通过</td>
                <td>{{ row.missing_critical.length ? row.missing_critical.join(', ') : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="hint">点击行查看该公司 fin_metric。</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.head h1 {
  margin: 0 0 8px;
  font-size: 24px;
}
.head p {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
  max-width: 720px;
}
.actions {
  display: flex;
  gap: 8px;
}
.ghost-btn,
.primary-btn {
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}
.ghost-btn {
  border: 1px solid var(--border);
  background: var(--surface);
}
.primary-btn {
  border: 0;
  background: #0f766e;
  color: #fff;
}
.quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}
.quick-link {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
  color: #2563eb;
  text-decoration: none;
  background: var(--surface);
}
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.stat-label {
  margin: 0 0 6px;
  font-size: 13px;
  color: var(--text-muted);
}
.stat-value {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
}
.stat-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
.panel h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
.table-wrap {
  overflow: auto;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
.clickable {
  cursor: pointer;
}
.clickable:hover {
  background: #f8fafc;
}
.mono {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
  color: var(--text-muted);
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.tag.ok {
  background: #ecfdf5;
  color: #047857;
}
.tag.fail {
  background: #fef2f2;
  color: #b91c1c;
}
.hint {
  color: var(--text-muted);
  font-size: 14px;
}
.error {
  color: #b91c1c;
}
.ok {
  color: #047857;
}
code {
  font-size: 12px;
}
@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
