export type ChatRole = 'user' | 'assistant'

export interface Citation {
  /** Agent 工具证据的原始编号（返回数组中可能不连续）；结构化风险卡片通过它绑定来源。 */
  citation_id?: number | null
  doc_id: string
  page: number
  snippet: string
  viewer_url?: string | null
  /** 文档展示标题（非文件名） */
  title?: string | null
  /** 应用内深链，如财务事实库 */
  href?: string | null
  /** document = 年报页；facts = 财务事实库；web = 外部公开网页 */
  kind?: string | null
  publisher?: string | null
  published_at?: string | null
  fetched_at?: string | null
  content_hash?: string | null
  source_tier?: 'official' | 'public_web' | string | null
  /** 财务事实引用的结构化定位信息。 */
  company_code?: string | null
  concept?: string | null
  year?: number | null
}

export interface RiskFinding {
  id?: string | null
  risk_type: string
  severity: 'low' | 'medium' | 'high'
  conclusion: string
  evidence_ids: number[]
  data_points: string[]
  uncertainty: string
  review_question: string
  review_status?: string | null
}

export interface RiskAuditResult {
  id?: string | null
  company_code: string
  company_name: string
  year: number
  status: 'completed' | 'partial' | 'insufficient_evidence'
  summary: string
  evidence_gaps: string[]
  findings: RiskFinding[]
}

export interface ChatRequest {
  message: string
  temperature?: number
  session_id?: string
  use_rag?: boolean
  model?: string
}

export interface PendingAsknum {
  intent?: string
  company?: string | null
  years?: number[]
  metric?: string | null
  scope?: string
  missing?: string[]
  hint?: string
}

export interface ComparisonClaim {
  statement: string
  citation_ids: number[]
}

export interface ComparisonCompanyResult {
  company_code: string
  company_name: string
  summary: string
  citation_ids: number[]
}

export interface CompanyComparisonResult {
  answer_type: 'company_comparison'
  comparison_allowed: boolean
  periods: number[]
  companies: ComparisonCompanyResult[]
  similarities: ComparisonClaim[]
  differences: ComparisonClaim[]
  missing_evidence: string[]
}

export interface ChatResponse {
  reply: string
  model: string
  disclaimer: string
  citations?: Citation[]
  session_id?: string | null
  rag_used?: boolean
  route?: string
  pending_node?: string | null
  pending_request?: PendingAsknum | null
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  /** 最终回答模型自身耗时 */
  latency_ms?: number
  /** Python 端路由、检索、重排、模型和校验的端到端总耗时 */
  total_latency_ms?: number
  comparison?: CompanyComparisonResult | null
}

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  model?: string
  disclaimer?: string
  citations?: Citation[]
  ragUsed?: boolean
  route?: string
  attachmentName?: string
  error?: boolean
  /** 本条消息 Token 数（用户为估算，AI 为 completion_tokens） */
  tokenCount?: number
  /** AI 回复时 RAG/系统提示等输入侧 Token */
  promptTokenCount?: number
  /** 最终回答模型自身耗时 */
  latencyMs?: number
  /** 完整请求耗时；回答框展示此值 */
  totalLatencyMs?: number
  /** 正在流式输出 */
  streaming?: boolean
  /** 流式等待时的状态文案 */
  statusText?: string
  /** Agent 单轮执行中的已完成阶段；最终结论仍放在 content */
  stages?: string[]
  /** 当前正在生成的阶段文本 */
  stageText?: string
  /** 多公司 RAG 的已校验结构化结果 */
  comparison?: CompanyComparisonResult | null
  /** 金融风险审计 Agent 保存的结构化初筛结果 */
  riskResult?: RiskAuditResult | null
  /** @deprecated 兼容旧缓存，请用 tokenCount */
  totalTokens?: number
}
