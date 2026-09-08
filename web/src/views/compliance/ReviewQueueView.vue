<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  approveTicket,
  createTicket,
  listTickets,
  rejectTicket,
  submitTicket,
  type ReviewTicket,
  type TicketStatus,
} from '../../api/reviews'
import { ApiRequestError } from '../../api/client'
import LoginPanel from '../../components/auth/LoginPanel.vue'
import { useAuth } from '../../composables/useAuth'
import { canReviewTickets, canSubmitTickets, deptLabel, roleLabel } from '../../config/user'

const { user, loggedIn } = useAuth()
const tickets = ref<ReviewTicket[]>([])
const loading = ref(false)
const error = ref('')
const hint = ref('')
const statusFilter = ref<TicketStatus | ''>('')
const selectedId = ref('')
const decideReason = ref('条款引用齐全')

const companyCode = ref('002594')
const title = ref('关联交易复核')
const reason = ref('需双人复核')
const conclusion = ref('并列查数后待合规确认')
const creating = ref(false)

const selected = computed(() => tickets.value.find((item) => item.id === selectedId.value) ?? tickets.value[0] ?? null)

const companies = computed(() => {
  if (user.value?.role === 'ANALYST') {
    return [
      { code: '002594', name: '比亚迪' },
      { code: '601633', name: '长城汽车' },
    ]
  }
  return [
    { code: '002594', name: '比亚迪' },
    { code: '601633', name: '长城汽车' },
    { code: '000333', name: '美的集团' },
    { code: '000651', name: '格力电器' },
  ]
})

function statusClass(status: string) {
  if (status === 'REVIEWED') return 'tag ok'
  if (status === 'REJECTED') return 'tag fail'
  if (status === 'SUBMITTED') return 'tag warn'
  return 'tag'
}

async function refresh() {
  if (!loggedIn.value) return
  if (user.value?.role === 'RM') {
    tickets.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    tickets.value = await listTickets(statusFilter.value || undefined)
    if (selectedId.value && !tickets.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = tickets.value[0]?.id ?? ''
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    tickets.value = []
  } finally {
    loading.value = false
  }
}

async function onCreate() {
  creating.value = true
  error.value = ''
  hint.value = ''
  try {
    const created = await createTicket({
      company_code: companyCode.value,
      title: title.value,
      reason: reason.value,
      conclusion: conclusion.value,
    })
    hint.value = created.replayed ? '幂等命中，返回已有工单' : '已创建 PENDING 草稿'
    selectedId.value = created.id
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建失败'
  } finally {
    creating.value = false
  }
}

async function onSubmit(ticket: ReviewTicket) {
  error.value = ''
  hint.value = ''
  try {
    await submitTicket(ticket.id)
    hint.value = '已提交，等待复核'
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败'
  }
}

async function onDecide(ticket: ReviewTicket, approve: boolean) {
  error.value = ''
  hint.value = ''
  try {
    await (approve ? approveTicket : rejectTicket)(ticket.id, decideReason.value || '复核意见')
    hint.value = approve ? '已通过（REVIEWED）' : '已驳回（REJECTED）'
    await refresh()
  } catch (err) {
    if (err instanceof ApiRequestError && err.errorCode === 'self_review') {
      error.value = '复核人不能等于提交人'
    } else {
      error.value = err instanceof Error ? err.message : '复核失败'
    }
  }
}

onMounted(refresh)
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <h1>合规复核</h1>
        <p>
          Agent / Python 只写 <code>PENDING</code> 草稿。提交、通过、驳回只在 Java：
          <code>PENDING → SUBMITTED → REVIEWED | REJECTED</code>。客户经理不能看工单，也不能复核。
          本页不经过 python-ai，问答挂了仍可建单和复核。
        </p>
      </div>
      <div class="actions">
        <button type="button" class="ghost-btn" :disabled="!loggedIn || loading" @click="refresh">刷新</button>
      </div>
    </header>

    <nav class="quick-links">
      <router-link to="/compliance/audit" class="quick-link">审计追踪</router-link>
      <router-link to="/settings/users" class="quick-link">登录 / 客户档案</router-link>
    </nav>

    <section v-if="!loggedIn" class="panel">
      <h2>先登录</h2>
      <p class="hint">分析师建单并提交，换合规员复核。客户经理登录后这里会拒绝。</p>
      <LoginPanel @logged-in="refresh" />
    </section>

    <template v-else>
      <p class="who">
        当前：{{ user?.displayName }} · {{ roleLabel(user?.role) }} · {{ deptLabel(user?.dept) }}
      </p>
      <p v-if="user?.role === 'RM'" class="error">
        客户经理不能创建或查看复核工单，也不能看投研内核年报。请到「用户与权限」查看对客档案。
      </p>

      <section v-if="canSubmitTickets(user?.role)" class="panel">
        <h2>新建草稿</h2>
        <div class="form-grid">
          <label>
            公司
            <select v-model="companyCode">
              <option v-for="item in companies" :key="item.code" :value="item.code">
                {{ item.code }} {{ item.name }}
              </option>
            </select>
          </label>
          <label>
            标题
            <input v-model="title" />
          </label>
          <label class="wide">
            原因
            <input v-model="reason" />
          </label>
          <label class="wide">
            结论
            <input v-model="conclusion" />
          </label>
        </div>
        <button type="button" class="primary-btn" :disabled="creating" @click="onCreate">
          {{ creating ? '创建中…' : '创建 PENDING' }}
        </button>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>工单队列</h2>
          <select v-model="statusFilter" @change="refresh">
            <option value="">全部</option>
            <option value="PENDING">PENDING</option>
            <option value="SUBMITTED">SUBMITTED</option>
            <option value="REVIEWED">REVIEWED</option>
            <option value="REJECTED">REJECTED</option>
          </select>
        </div>
        <p v-if="hint" class="ok">{{ hint }}</p>
        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="loading" class="hint">加载中…</p>
        <p v-else-if="!tickets.length" class="hint">暂无工单。</p>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>状态</th>
                <th>公司</th>
                <th>标题</th>
                <th>部门</th>
                <th>提交人</th>
                <th>复核人</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in tickets"
                :key="row.id"
                class="clickable"
                :class="{ active: selected?.id === row.id }"
                @click="selectedId = row.id"
              >
                <td><span :class="statusClass(row.status)">{{ row.status }}</span></td>
                <td class="mono">{{ row.companyCode }}</td>
                <td>{{ row.title }}</td>
                <td>{{ deptLabel(row.dept) }}</td>
                <td>{{ row.submittedBy || '—' }}</td>
                <td>{{ row.reviewedBy || '—' }}</td>
                <td>
                  <button
                    v-if="row.status === 'PENDING' && canSubmitTickets(user?.role)"
                    type="button"
                    class="ghost-btn"
                    @click.stop="onSubmit(row)"
                  >
                    提交
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="selected" class="panel">
        <h2>工单详情</h2>
        <dl class="info-grid">
          <div>
            <dt>ID</dt>
            <dd class="mono">{{ selected.id }}</dd>
          </div>
          <div>
            <dt>原因</dt>
            <dd>{{ selected.reason }}</dd>
          </div>
          <div>
            <dt>结论</dt>
            <dd>{{ selected.conclusion || '—' }}</dd>
          </div>
          <div>
            <dt>复核意见</dt>
            <dd>{{ selected.reviewReason || '—' }}</dd>
          </div>
        </dl>
        <div v-if="selected.status === 'SUBMITTED' && canReviewTickets(user?.role)" class="decide">
          <input v-model="decideReason" placeholder="复核意见" />
          <button type="button" class="primary-btn" @click="onDecide(selected, true)">通过</button>
          <button type="button" class="ghost-btn" @click="onDecide(selected, false)">驳回</button>
        </div>
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
  color: var(--muted);
  font-size: 14px;
  max-width: 760px;
}
.actions,
.quick-links {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.quick-links {
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
.who {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--muted);
}
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 16px;
}
.panel h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
.panel-head h2 {
  margin: 0;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 12px;
}
.form-grid label,
.decide input,
select,
input {
  display: grid;
  gap: 4px;
  font-size: 13px;
  color: var(--muted);
}
.wide {
  grid-column: 1 / -1;
}
input,
select {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
  color: var(--text-strong);
  background: #fff;
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
.clickable:hover,
.clickable.active {
  background: #f8fafc;
}
.mono {
  font-family: var(--mono);
  font-size: 12px;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  background: #f1f5f9;
  color: #475569;
}
.tag.ok {
  background: #ecfdf5;
  color: #047857;
}
.tag.fail {
  background: #fef2f2;
  color: #b91c1c;
}
.tag.warn {
  background: #fffbeb;
  color: #b45309;
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin: 0 0 12px;
}
.info-grid dt {
  font-size: 12px;
  color: #94a3b8;
}
.info-grid dd {
  margin: 4px 0 0;
}
.decide {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.decide input {
  flex: 1;
  min-width: 220px;
}
.hint {
  color: var(--muted);
  font-size: 14px;
}
.error {
  color: #b91c1c;
}
.ok {
  color: #047857;
}
@media (max-width: 800px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
