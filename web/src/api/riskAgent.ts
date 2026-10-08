import { API_BASE, apiFetch, authHeaders, ensureRequestId, formatErrorDetail, rememberResponseRequestId, ApiRequestError } from './client'
import type { Citation, RiskAuditResult } from '../types/chat'

export interface RiskAgentThread {
  id: string
  title: string
  status: string
  updatedAt: number
  messages: Array<{
    id: string
    author: string
    chunks: Array<{ kind: string; text?: string }>
    citations?: Citation[]
    risk_result?: RiskAuditResult | null
  }>
}

export function listRiskAgentThreads(): Promise<RiskAgentThread[]> {
  return apiFetch('/risk-agent/threads')
}

export function getRiskAgentHealth(): Promise<{ ok: boolean }> {
  return apiFetch('/risk-agent/health')
}

export interface AgentRunItem {
  run_id: string
  thread_id: string
  title: string
  session_title: string
  status: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  error: string | null
}

export interface AgentRunListResponse {
  total: number
  limit: number
  offset: number
  sessions: Array<{ thread_id: string; title: string; run_count: number; latest_run_at: string }>
  summary: {
    completed: number
    failed: number
    running: number
    avg_duration_ms: number
  }
  items: AgentRunItem[]
}

export function listAgentRuns(limit = 50, offset = 0, threadId: string | null = null): Promise<AgentRunListResponse> {
  const filter = threadId ? `&thread_id=${encodeURIComponent(threadId)}` : ''
  return apiFetch(`/risk-agent/monitor/runs?limit=${limit}&offset=${offset}${filter}`)
}

export interface AgentTraceEvent {
  id: string
  phase: 'user' | 'model' | 'tool' | 'subagent'
  label: string
  status: 'running' | 'completed' | 'failed'
  started_at: string
  finished_at: string | null
}

export interface AgentRunTrace {
  run_id: string
  thread_id: string
  title: string
  session_title: string
  status: string
  started_at: string
  finished_at: string | null
  error: string | null
  events: AgentTraceEvent[]
}

export function getAgentRunTrace(runId: string): Promise<AgentRunTrace> {
  return apiFetch(`/risk-agent/monitor/runs/${encodeURIComponent(runId)}/trace`)
}

export interface RiskAgentOptions {
  models: Array<{ id: string; label: string }>
  default_agent_model: string | null
}

export function getRiskAgentOptions(): Promise<RiskAgentOptions> {
  return apiFetch('/risk-agent/options')
}

export function getRiskAgentThread(id: string): Promise<RiskAgentThread> {
  return apiFetch(`/risk-agent/threads/${encodeURIComponent(id)}`)
}

export function deleteRiskAgentThread(id: string): Promise<void> {
  return apiFetch(`/risk-agent/threads/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export type RiskAgentEvent = { event: string; data: Record<string, unknown> }

function decodeSseBlock(block: string): RiskAgentEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (dataLines.length === 0) return null
  const parsed: unknown = JSON.parse(dataLines.join('\n'))
  return { event, data: parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {} }
}

export async function streamRiskAgentMessage(
  threadId: string | null,
  content: string,
  modelId: string,
  onEvent: (event: RiskAgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const path = threadId
    ? `/risk-agent/threads/${encodeURIComponent(threadId)}/stream-message`
    : '/risk-agent/threads/stream-message'
  // 成功响应是 SSE；上游在流建立前失败时由 Java BFF 返回 JSON 错误。
  // 同时声明两种类型，避免 Spring 因只接受 SSE 而把原始 4xx/5xx 再变成 500。
  const headers = authHeaders({
    'Content-Type': 'application/json',
    Accept: 'text/event-stream, application/json',
  })
  ensureRequestId(headers)
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST', headers, body: JSON.stringify({ content, model_id: modelId }), signal,
  })
  rememberResponseRequestId(response)
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown }
    throw new ApiRequestError(formatErrorDetail(body.detail, response.status), response.status)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sawDone = false
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
      buffer = buffer.replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const item = decodeSseBlock(block)
        if (item?.event === 'error') {
          throw new Error(String(item.data.detail || item.data.message || 'Agent 运行失败'))
        }
        if (item?.event === 'done') sawDone = true
        if (item) onEvent(item)
        boundary = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    if (buffer.trim()) {
      const item = decodeSseBlock(buffer)
      if (item?.event === 'error') throw new Error(String(item.data.detail || 'Agent 运行失败'))
      if (item?.event === 'done') sawDone = true
      if (item) onEvent(item)
    }
    if (!sawDone) throw new Error('Agent 流式响应中断，请稍后打开会话确认执行状态')
  } catch (error) {
    await reader.cancel().catch(() => {})
    throw error
  } finally {
    reader.releaseLock()
  }
}
