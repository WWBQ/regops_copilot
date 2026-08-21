export interface NavItem {
  id: string
  label: string
  path: string
  /** 计划阶段标签，如 W2+、W9+ */
  phase?: string
  enabled?: boolean
}

export interface NavGroup {
  id: string
  label: string
  items: NavItem[]
}

/** 侧边栏菜单（页面占位，按 RegOps 数据流分组） */
export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'qa',
    label: '问答',
    items: [
      { id: 'chat', label: '合规问答', path: '/', enabled: true },
    ],
  },
  {
    id: 'quality',
    label: '数据质量',
    items: [
      { id: 'quality-gates', label: '质量门 G1/G2/G3', path: '/quality/gates', phase: 'W2-2' },
      { id: 'human-review', label: '数据标注', path: '/quality/review', enabled: true },
      { id: 'fin-metrics', label: '财务事实库', path: '/quality/facts', phase: 'W2-4' },
    ],
  },
  {
    id: 'compliance',
    label: '合规业务',
    items: [
      { id: 'review', label: '合规复核', path: '/compliance/review', phase: 'W9+' },
      { id: 'workflow', label: '审批流', path: '/compliance/workflow', phase: 'W9+' },
      { id: 'audit', label: '审计追踪', path: '/compliance/audit', phase: 'W9+' },
    ],
  },
  {
    id: 'ops',
    label: '运维监控',
    items: [
      { id: 'ingest-monitor', label: '解析监控', path: '/ops/ingest', phase: 'W2-5' },
      { id: 'logs', label: '日志监控', path: '/ops/logs', phase: 'W2+' },
      { id: 'health', label: '系统健康', path: '/ops/health', phase: 'W1' },
      { id: 'eval', label: '评估报告', path: '/ops/eval', phase: 'W1-4' },
    ],
  },
]

export const PLACEHOLDER_PAGES: Record<
  string,
  { title: string; summary: string; backend?: string; phase: string }
> = {
  rag: {
    title: '合规问答',
    summary: '已合并至首页：通用合规对话 + 年报 RAG + 上传 PDF 会话问答。',
    backend: 'POST /chat',
    phase: 'W2-6',
  },
  'ingest-monitor': {
    title: '解析监控',
    summary:
      'Docling 解析进度、页数/表格统计、ingest_job 失败重试与 content_hash 去重。批量入库走 CLI，会话上传在合规问答。',
    backend: 'ingest_job + parser/cleaner 指标',
    phase: 'W2-5',
  },
  'quality-gates': {
    title: '质量门 G1/G2/G3',
    summary: '金额一致性、财务勾稽、证据坐标（page + bbox）拦截看板。',
    backend: 'docs/INGEST_VALIDATION.md',
    phase: 'W2-2',
  },
  'human-review': {
    title: '数据标注',
    summary: '上传 Excel/JSON，核对 PDF/HTML/文本并保存标注；问 AI 走 POST /chat。',
    backend: 'python-ai /labeling/* + /chat',
    phase: 'W1+',
  },
  'fin-metrics': {
    title: '财务事实库',
    summary: 'Financial Fact / fin_metric 浏览与导出。',
    phase: 'W2-4',
  },
  review: {
    title: '合规复核',
    summary: 'Maker-Checker 复核界面，结论留痕。',
    backend: 'java-service',
    phase: 'W9+',
  },
  workflow: {
    title: '审批流',
    summary: '制度条款变更、异常交易等审批工单。',
    phase: 'W9+',
  },
  audit: {
    title: '审计追踪',
    summary: 'Correlation ID 跨链路、操作人、时间戳。',
    phase: 'W9+',
  },
  logs: {
    title: '日志监控',
    summary: 'ingest / chat / RAG / Agent 结构化日志与错误聚合。',
    phase: 'W2+',
  },
  health: {
    title: '系统健康',
    summary: 'python-ai、java-service、PostgreSQL、pgvector 探活。',
    backend: '/health',
    phase: 'W1',
  },
  eval: {
    title: '评估报告',
    summary: 'W1 chat 黄金集、W2 检索集回归报告。',
    backend: 'eval/run_w1_chat.py',
    phase: 'W1-4',
  },
  settings: {
    title: '设置',
    summary: '模型切换、温度、Embedding 配置（只读展示，密钥不进前端）。',
    phase: 'W9+',
  },
  users: {
    title: '用户与权限',
    summary: 'RBAC、角色、数据域隔离。',
    backend: 'java-service Security',
    phase: 'W9+',
  },
}
