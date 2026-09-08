import { API_BASE, apiFetch, authHeaders, ensureRequestId, formatErrorDetail, rememberResponseRequestId, ApiRequestError } from './client'
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
    thread_id: raw.thread_id ?? (raw as { threadId?: string }).threadId,
    pending_node: raw.pending_node ?? (raw as { pendingNode?: string }).pendingNode,
  }
}

function chatBody(body: ChatRequest): string {
  return JSON.stringify({
    message: body.message,
    temperature: body.temperature ?? 0.1,
    session_id: body.session_id,
    use_rag: body.use_rag ?? true,
    model: body.model,
    thread_id: body.thread_id,
  })
}

type SseEvent = { event: string; data: string }

function takeSseEvents(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = []
  let rest = buffer.replace(/\r\n/g, '\n')
  while (true) {
    const split = rest.indexOf('\n\n')
    if (split < 0) {
      break
    }
    const raw = rest.slice(0, split)
    rest = rest.slice(split + 2)
    let event = 'message'
    const dataLines: string[] = []
    for (const line of raw.split('\n')) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }
    if (dataLines.length > 0) {
      events.push({ event, data: dataLines.join('\n') })
    }
  }
  return { events, rest }
}

export type BffHealthResponse = {
  status: string
  service?: string
  pythonAi?: {
    status?: string
    error?: string
    error_code?: string
    service?: string
  }
}

export function getHealth(): Promise<BffHealthResponse> {
  return apiFetch('/health')
}

export function getModels(): Promise<{ available: string[]; default?: string | null }> {
  return apiFetch('/models')
}

export function postChat(body: ChatRequest): Promise<ChatResponse> {
  return apiFetch<RawChatResponse>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: chatBody(body),
  }).then(normalizeChatResponse)
}

export type ChatStreamHandlers = {
  signal?: AbortSignal
  onStatus?: (text: string) => void | Promise<void>
  onMeta?: (meta: {
    route?: string
    model?: string
    session_id?: string | null
    thread_id?: string | null
  }) => void | Promise<void>
  onDelta?: (text: string) => void | Promise<void>
}

const CJK_RE = /[\u3400-\u9fff]/

export function splitVisibleChunks(text: string): string[] {
  if (!text) {
    return []
  }
  const maxWeight = text.length > 240 ? 6 : 2
  const chunks: string[] = []
  let buf = ''
  let weight = 0
  for (const char of text) {
    buf += char
    weight += CJK_RE.test(char) ? 2 : 1
    if (weight >= maxWeight || char === '\n') {
      chunks.push(buf)
      buf = ''
      weight = 0
    }
  }
  if (buf) {
    chunks.push(buf)
  }
  return chunks
}

function yieldFrame(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 28)
  })
}

async function emitDelta(handlers: ChatStreamHandlers, text: string): Promise<void> {
  for (const piece of splitVisibleChunks(text)) {
    if (handlers.signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError')
    }
    await handlers.onDelta?.(piece)
    await yieldFrame()
  }
}

export async function streamChat(body: ChatRequest, handlers: ChatStreamHandlers = {}): Promise<ChatResponse> {
  const headers = authHeaders({
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  })
  ensureRequestId(headers)
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers,
    body: chatBody(body),
    signal: handlers.signal,
  })
  rememberResponseRequestId(response)
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: unknown
      extra?: { error_code?: string; request_id?: string }
    }
    throw new ApiRequestError(
      formatErrorDetail(payload.detail, response.status),
      response.status,
      payload.extra?.error_code,
      payload.extra?.request_id ?? response.headers.get('X-Request-ID') ?? undefined,
    )
  }
  if (!response.body) {
    throw new Error('浏览器未提供流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed: ChatResponse | null = null

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const taken = takeSseEvents(buffer)
      buffer = taken.rest
      for (const item of taken.events) {
        let parsed: unknown = item.data
        try {
          parsed = JSON.parse(item.data)
        } catch {
          parsed = item.data
        }
        if (item.event === 'error') {
          const err = parsed as { detail?: unknown; status?: number; extra?: { error_code?: string; request_id?: string } }
          throw new ApiRequestError(
            formatErrorDetail(err.detail, err.status ?? 502),
            err.status ?? 502,
            err.extra?.error_code,
            err.extra?.request_id ?? response.headers.get('X-Request-ID') ?? undefined,
          )
        }
        if (item.event === 'status' && parsed && typeof parsed === 'object' && 'text' in parsed) {
          await handlers.onStatus?.(String((parsed as { text: string }).text))
        } else if (item.event === 'meta' && parsed && typeof parsed === 'object') {
          await handlers.onMeta?.(parsed as { route?: string; model?: string; session_id?: string | null })
        } else if (item.event === 'delta' && parsed && typeof parsed === 'object' && 'text' in parsed) {
          await emitDelta(handlers, String((parsed as { text: string }).text))
        } else if (item.event === 'done' && parsed && typeof parsed === 'object') {
          completed = normalizeChatResponse(parsed as RawChatResponse)
        }
      }
    }
  } finally {
    reader.releaseLock()
  }

  if (!completed) {
    throw new Error('连接中断，未收到完整回复')
  }
  return completed
}
