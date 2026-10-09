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
      { id: 'risk-agent', label: '金融风险审计助手', path: '/risk-agent', enabled: true },
      { id: 'ai-coding', label: 'AI Coding', path: '/ai-coding', enabled: true },
    ],
  },
  {
    id: 'quality',
    label: '数据质量',
    items: [
      { id: 'quality-data', label: '财务数据', path: '/quality/gates', enabled: true },
      { id: 'human-review', label: '数据审核', path: '/quality/review/pending', enabled: true },
    ],
  },
  {
    id: 'ops',
    label: '运维监控',
    items: [
      { id: 'ingest-monitor', label: '解析监控', path: '/ops/ingest', phase: 'W2-5', enabled: true },
      { id: 'runtime-monitor', label: '问答与 Agent 监控', path: '/ops/monitor/rag', enabled: true },
      { id: 'health', label: '系统健康', path: '/ops/health', phase: 'W1', enabled: true },
      { id: 'eval', label: '评估报告', path: '/ops/eval', phase: 'W1-4', enabled: true },
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
      'Docling 解析进度、页数/chunk 统计、ingest_job 与会话上传状态；批量入库走 CLI，会话上传在合规问答。',
    backend: 'GET /api/ops/ingest/overview',
    phase: 'W2-5',
  },
  'rag-monitor': {
    title: 'RAG 检索监控',
    summary:
      '每次问答的 Hybrid 检索 trace：关键词、向量/关键词召回、RRF、精排、最终 top-k 片段与拒答率。',
    backend: 'GET /api/ops/rag-traces（含 summary 拒答率）',
    phase: 'W3',
  },
  'asknum-monitor': {
    title: '问数监控',
    summary:
      '首页问数 lookup 的 trace：路由、公司/指标槽位、lookup 结果与是否拦截数字。评测不写此表。',
    backend: 'GET /api/ops/asknum-traces',
    phase: 'W4',
  },
  'quality-gates': {
    title: '质量门 G1/G2/G3',
    summary: 'G1 金额一致性、G2 勾稽（R01–R03）、G3 结构化溯源；F10 JSON 写入 fin_metric。',
    backend: 'GET /api/ops/quality/gates · POST /api/ops/quality/ingest',
    phase: 'W2-2',
  },
  'human-review': {
    title: '数据审核',
    summary: '质量门未通过的财务事实进入待审核队列；记录修订金额、审核依据、决定与审核人。',
    backend: 'GET /api/quality/reviews · POST /api/quality/facts/{id}/review',
    phase: 'W2',
  },
  'fin-metrics': {
    title: '财务事实库',
    summary: 'Financial Fact / fin_metric 浏览与导出。',
    backend: 'GET /api/ops/quality/facts',
    phase: 'W2-2',
  },
  health: {
    title: '系统健康',
    summary: 'BFF 请求量、5xx、响应耗时与 JVM 压力；检查 Java、Python、PostgreSQL、Redis、RabbitMQ 等依赖。',
    backend: 'GET /api/ops/system/overview',
    phase: 'W1',
  },
  eval: {
    title: '评估报告',
    summary: '选择聊天、RAG、问数评测任务，一键运行并查看 Recall@k、准确率与明细。',
    backend: 'POST /api/ops/eval/runs',
    phase: 'W1-4',
  },
  'agent-monitor': {
    title: 'Agent 监控',
    summary: '金融风险审计助手的运行状态、耗时与失败记录。',
    backend: 'GET /api/risk-agent/monitor/runs',
    phase: 'W9',
  },
  settings: {
    title: '设置',
    summary: '模型切换、温度、Embedding 配置（只读展示，密钥不进前端）。',
    phase: 'W9+',
  },
  users: {
    title: '用户与权限',
    summary: 'JWT 登录、角色与年报数据域。不同部门只能检索和预览授权公司文档。',
    backend: 'POST /api/auth/login · GET /api/auth/me',
    phase: 'W7',
  },
}
