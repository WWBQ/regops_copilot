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
      { id: 'quality-gates', label: '质量门 G1/G2/G3', path: '/quality/gates', phase: 'W2-2', enabled: true },
      { id: 'human-review', label: '数据标注', path: '/quality/review', enabled: true },
      { id: 'fin-metrics', label: '财务事实库', path: '/quality/facts', phase: 'W2-4', enabled: true },
    ],
  },
  {
    id: 'compliance',
    label: '合规业务',
    items: [
      { id: 'review', label: '合规复核', path: '/compliance/review', phase: 'W7', enabled: true },
      { id: 'workflow', label: '审批流', path: '/compliance/workflow', phase: 'W7', enabled: true },
      { id: 'audit', label: '审计追踪', path: '/compliance/audit', phase: 'W7', enabled: true },
    ],
  },
  {
    id: 'ops',
    label: '运维监控',
    items: [
      { id: 'ingest-monitor', label: '解析监控', path: '/ops/ingest', phase: 'W2-5', enabled: true },
      { id: 'rag-monitor', label: 'RAG 检索监控', path: '/ops/rag', phase: 'W3', enabled: true },
      { id: 'asknum-monitor', label: '问数监控', path: '/ops/asknum', phase: 'W4', enabled: true },
      { id: 'llm-trace', label: 'LLM Trace', path: '/ops/traces', phase: 'W9', enabled: true },
      { id: 'logs', label: '日志监控', path: '/ops/logs', phase: 'W2+', enabled: true },
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
    title: '数据标注',
    summary: '上传 Excel/JSON，核对 PDF/HTML/文本并保存标注；问 AI 走 POST /chat。',
    backend: 'python-ai /labeling/* + /chat',
    phase: 'W1+',
  },
  'fin-metrics': {
    title: '财务事实库',
    summary: 'Financial Fact / fin_metric 浏览与导出。',
    backend: 'GET /api/ops/quality/facts',
    phase: 'W2-2',
  },
  review: {
    title: '合规复核',
    summary: 'Java maker-checker：PENDING 草稿提交后由他人复核为 REVIEWED / REJECTED。',
    backend: 'POST /api/reviews/tickets · /submit · /approve · /reject',
    phase: 'W7',
  },
  workflow: {
    title: '审批流',
    summary: '与合规复核同一状态机：PENDING → SUBMITTED → REVIEWED | REJECTED，状态不能倒流。',
    backend: 'java-service ReviewService',
    phase: 'W7',
  },
  audit: {
    title: '审计追踪',
    summary: '操作人、时间、前后快照、X-Request-ID。',
    backend: 'GET /api/audit/events',
    phase: 'W7',
  },
  logs: {
    title: '日志监控',
    summary: 'ingest 失败、会话上传异常、RAG 非成功 trace 的结构化事件聚合。',
    backend: 'GET /api/ops/logs/events',
    phase: 'W2+',
  },
  health: {
    title: '系统健康',
    summary: 'Java / Python / PostgreSQL / pgvector 探活，语料库、入库任务、RAG trace 与配置概览。',
    backend: 'GET /api/ops/system/overview',
    phase: 'W1',
  },
  eval: {
    title: '评估报告',
    summary: '选择评测任务（W1 聊天 / RAG 检索 / 红队），一键运行并查看 Recall@k、准确率与明细。',
    backend: 'POST /api/ops/eval/runs',
    phase: 'W1-4',
  },
  'llm-trace': {
    title: 'LLM Trace',
    summary: 'Prompt 版本、Token、估算成本与 W3C Trace ID。未配 Langfuse 时使用进程内缓冲。',
    backend: 'GET /api/ops/obs/traces',
    phase: 'W9',
  },
  agent: {
    title: '合规问答（多步）',
    summary:
      'W6 多步编排接在同一助手里：对比 + 核对口径走任务 Checkpoint，不另开对话页。工具仍是 lookup_metric / RAG。',
    backend: 'python-ai/app/agents/（规划，入口为 /）',
    phase: 'W6',
  },
  settings: {
    title: '设置',
    summary: '模型切换、温度、Embedding 配置（只读展示，密钥不进前端）。',
    phase: 'W9+',
  },
  users: {
    title: '用户与权限',
    summary: 'JWT 登录、角色与客户档案数据域。客户经理看不到投研内核。',
    backend: 'POST /api/auth/login · GET /api/customers',
    phase: 'W7',
  },
}
