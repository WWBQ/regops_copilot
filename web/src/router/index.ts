import { createRouter, createWebHistory } from 'vue-router'

import ChatPanel from '../components/chat/ChatPanel.vue'
import AuthGateView from '../views/account/AuthGateView.vue'
import { getAuthToken } from '../api/client'
import { useAuth } from '../composables/useAuth'
import { ApiRequestError } from '../api/client'
import RiskAgentView from '../views/agent/RiskAgentView.vue'
import DocumentViewerView from '../views/documents/DocumentViewerView.vue'
import SystemHealthView from '../views/ops/SystemHealthView.vue'
import EvalReportView from '../views/ops/EvalReportView.vue'
import MonitorView from '../views/ops/MonitorView.vue'
import ProfileView from '../views/account/ProfileView.vue'
import UsersPermissionsView from '../views/account/UsersPermissionsView.vue'
import PlaceholderView from '../views/PlaceholderView.vue'
import QualityGatesView from '../views/quality/QualityGatesView.vue'
import FinMetricsView from '../views/quality/FinMetricsView.vue'
import CreateTaskView from '../views/labeling/CreateTaskView.vue'
import LabelWorkspaceView from '../views/labeling/LabelWorkspaceView.vue'
import TaskHallView from '../views/labeling/TaskHallView.vue'
import TaskItemsView from '../views/labeling/TaskItemsView.vue'
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: AuthGateView,
      meta: { title: '登录 / 注册' },
    },
    {
      path: '/',
      name: 'chat',
      component: ChatPanel,
      meta: { title: '合规问答' },
    },
    {
      path: '/risk-agent',
      name: 'risk-agent',
      component: RiskAgentView,
      meta: { title: '金融风险审计助手' },
    },
    {
      path: '/rag',
      redirect: '/',
    },
    {
      path: '/ingest',
      redirect: '/ops/ingest',
    },
    {
      path: '/ingest/monitor',
      redirect: '/ops/ingest',
    },
    {
      path: '/ingest/jobs',
      redirect: '/ops/ingest',
    },
    {
      path: '/ops/ingest',
      name: 'ingest-monitor',
      component: () => import('../views/ops/IngestMonitorView.vue'),
      meta: { title: '解析监控', pageId: 'ingest-monitor', group: 'ops' },
    },
    {
      path: '/ops/rag',
      redirect: '/ops/monitor/rag',
    },
    {
      path: '/ops/asknum',
      redirect: '/ops/monitor/asknum',
    },
    {
      path: '/ops/monitor',
      redirect: '/ops/monitor/rag',
    },
    {
      path: '/ops/monitor/rag',
      name: 'rag-monitor',
      component: MonitorView,
      meta: { title: 'RAG 检索监控', pageId: 'rag-monitor', group: 'ops' },
    },
    {
      path: '/ops/monitor/asknum',
      name: 'asknum-monitor',
      component: MonitorView,
      meta: { title: '问数监控', pageId: 'asknum-monitor', group: 'ops' },
    },
    {
      path: '/ops/monitor/agent',
      name: 'agent-monitor',
      component: MonitorView,
      meta: { title: 'Agent 监控', pageId: 'agent-monitor', group: 'ops' },
    },
    {
      path: '/ops/traces',
      redirect: '/ops/monitor/agent',
    },
    {
      path: '/quality/gates',
      name: 'quality-gates',
      component: QualityGatesView,
      meta: { title: '质量门', pageId: 'quality-gates', group: 'quality' },
    },
    {
      path: '/quality/review',
      name: 'human-review',
      component: TaskHallView,
      meta: { title: '数据标注' },
    },
    {
      path: '/quality/review/create',
      name: 'label-create',
      component: CreateTaskView,
      meta: { title: '创建标注任务' },
    },
    {
      path: '/quality/review/:taskId/:idx',
      name: 'label-item',
      component: LabelWorkspaceView,
      meta: { title: '标注条目' },
    },
    {
      path: '/quality/review/:taskId',
      name: 'label-items',
      component: TaskItemsView,
      meta: { title: '标注列表' },
    },
    {
      path: '/quality/facts',
      name: 'fin-metrics',
      component: FinMetricsView,
      meta: { title: '财务事实库', pageId: 'fin-metrics', group: 'quality' },
    },
    {
      path: '/compliance/audit',
      redirect: '/risk-agent',
    },
    {
      path: '/compliance/audit/risks',
      redirect: '/risk-agent',
    },
    {
      path: '/compliance/audit/events',
      redirect: '/risk-agent',
    },
    {
      path: '/ops/logs',
      redirect: '/ops/monitor/rag',
    },
    {
      path: '/ops/health',
      name: 'health',
      component: SystemHealthView,
      meta: { title: '系统健康', pageId: 'health', group: 'ops' },
    },
    {
      path: '/ops/eval',
      name: 'eval',
      component: EvalReportView,
      meta: { title: '评估报告', pageId: 'eval', group: 'ops' },
    },
    {
      path: '/documents/:docId/view',
      name: 'document-viewer',
      component: DocumentViewerView,
      meta: { title: '文档预览' },
    },
    {
      path: '/account/profile',
      name: 'profile',
      component: ProfileView,
      meta: { title: '个人资料' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: PlaceholderView,
      meta: { title: '设置', pageId: 'settings' },
    },
    {
      path: '/settings/users',
      name: 'users',
      component: UsersPermissionsView,
      meta: { title: '用户与权限', pageId: 'users' },
    },
  ],
})

let validatedToken = ''
router.beforeEach(async (to) => {
  const auth = useAuth()
  const token = getAuthToken()
  if (to.path === '/login') return token && auth.loggedIn.value ? '/' : true
  if (!token || !auth.loggedIn.value) return { path: '/login', query: { redirect: to.fullPath } }
  if (validatedToken !== token) {
    try {
      await auth.refreshMe()
      validatedToken = token
    } catch (error) {
      if (error instanceof ApiRequestError && [401, 403].includes(error.status)) {
        auth.logout()
        return { path: '/login', query: { redirect: to.fullPath } }
      }
      // 网络暂时不可用时保留现有凭据；后端仍会验证每个业务请求。
    }
    if (!auth.loggedIn.value) return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'RegOps Copilot'
  document.title = `${title} · RegOps Copilot`
})

export default router
