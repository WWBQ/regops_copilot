import { apiFetch } from './client'
import type { ChatRequest, ChatResponse } from '../types/chat'

type RawChatResponse = ChatResponse & {
  totalTokens?: number
  latencyMs?: number
  promptTokens?: number
  completionTokens?: number
}

function normalizeChatResponse(raw: RawChatResponse): ChatResponse {
  return {
    ...raw,
    prompt_tokens: raw.prompt_tokens ?? raw.promptTokens,
    completion_tokens: raw.completion_tokens ?? raw.completionTokens,
    total_tokens: raw.total_tokens ?? raw.totalTokens,
    latency_ms: raw.latency_ms ?? raw.latencyMs,
    rag_used: raw.rag_used ?? (raw as { ragUsed?: boolean }).ragUsed,
    session_id: raw.session_id ?? (raw as { sessionId?: string }).sessionId,
  }
}

export function getHealth(): Promise<{ status: string }> {
  return apiFetch('/health')
}

export function getModels(): Promise<{ available: string[] }> {
  return apiFetch('/models')
}

export function postChat(body: ChatRequest): Promise<ChatResponse> {
  return apiFetch<RawChatResponse>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: body.message,
      temperature: body.temperature ?? 0.1,
      session_id: body.session_id,
      use_rag: body.use_rag ?? true,
      model: body.model,
    }),
  }).then(normalizeChatResponse)
}
