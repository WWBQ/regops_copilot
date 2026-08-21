import { createRouter, createWebHistory } from 'vue-router'

import ChatPanel from '../components/chat/ChatPanel.vue'
import DocumentViewerView from '../views/documents/DocumentViewerView.vue'
import SystemHealthView from '../views/ops/SystemHealthView.vue'
import IngestMonitorView from '../views/ops/IngestMonitorView.vue'
import LogsMonitorView from '../views/ops/LogsMonitorView.vue'
import EvalReportView from '../views/ops/EvalReportView.vue'
import RagMonitorView from '../views/ops/RagMonitorView.vue'
import ProfileView from '../views/account/ProfileView.vue'
import PlaceholderView from '../views/PlaceholderView.vue'
import CreateTaskView from '../views/labeling/CreateTaskView.vue'
import LabelWorkspaceView from '../views/labeling/LabelWorkspaceView.vue'
import TaskHallView from '../views/labeling/TaskHallView.vue'
import TaskItemsView from '../views/labeling/TaskItemsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'chat',
      component: ChatPanel,
      meta: { title: '合规问答' },
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
      component: IngestMonitorView,
      meta: { title: '解析监控', pageId: 'ingest-monitor', group: 'ops' },
    },
    {
      path: '/ops/rag',
      name: 'rag-monitor',
      component: RagMonitorView,
      meta: { title: 'RAG 检索监控', pageId: 'rag-monitor', group: 'ops' },
    },
    {
      path: '/quality/gates',
      name: 'quality-gates',
      component: PlaceholderView,
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
      component: PlaceholderView,
      meta: { title: '财务事实库', pageId: 'fin-metrics', group: 'quality' },
    },
    {
      path: '/compliance/review',
      name: 'compliance-review',
      component: PlaceholderView,
      meta: { title: '合规复核', pageId: 'review' },
    },
    {
      path: '/compliance/workflow',
      name: 'workflow',
      component: PlaceholderView,
      meta: { title: '审批流', pageId: 'workflow' },
    },
    {
      path: '/compliance/audit',
      name: 'audit',
      component: PlaceholderView,
      meta: { title: '审计追踪', pageId: 'audit' },
    },
    {
      path: '/ops/logs',
      name: 'logs',
      component: LogsMonitorView,
      meta: { title: '日志监控', pageId: 'logs', group: 'ops' },
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
      component: PlaceholderView,
      meta: { title: '用户与权限', pageId: 'users' },
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'RegOps Copilot'
  document.title = `${title} · RegOps Copilot`
})

export default router
