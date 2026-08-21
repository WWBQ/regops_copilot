export type ChatRole = 'user' | 'assistant'

export interface Citation {
  doc_id: string
  page: number
  snippet: string
  viewer_url?: string | null
  /** 文档展示标题（非文件名） */
  title?: string | null
}

export interface ChatRequest {
  message: string
  temperature?: number
  session_id?: string
  use_rag?: boolean
  model?: string
}

export interface ChatResponse {
  reply: string
  model: string
  disclaimer: string
  citations?: Citation[]
  session_id?: string | null
  rag_used?: boolean
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
  attachmentName?: string
  error?: boolean
  /** 本条消息 Token 数（用户为估算，AI 为 completion_tokens） */
  tokenCount?: number
  /** AI 回复时 RAG/系统提示等输入侧 Token */
  promptTokenCount?: number
  latencyMs?: number
  /** @deprecated 兼容旧缓存，请用 tokenCount */
  totalTokens?: number
}
