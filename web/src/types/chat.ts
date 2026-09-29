export type ChatRole = 'user' | 'assistant'

export interface Citation {
  doc_id: string
  page: number
  snippet: string
  viewer_url?: string | null
  /** 文档展示标题（非文件名） */
  title?: string | null
  /** 应用内深链，如财务事实库 */
  href?: string | null
  /** document = 年报页；facts = 财务事实库 */
  kind?: string | null
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
  latency_ms?: number
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
  latencyMs?: number
  /** 正在流式输出 */
  streaming?: boolean
  /** 流式等待时的状态文案 */
  statusText?: string
  /** @deprecated 兼容旧缓存，请用 tokenCount */
  totalTokens?: number
}
