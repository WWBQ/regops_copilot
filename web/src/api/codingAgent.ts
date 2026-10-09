import { API_BASE, ApiRequestError, apiFetch, authHeaders, ensureRequestId, formatErrorDetail, rememberResponseRequestId } from './client'
import { streamAgentMessage, type RiskAgentEvent, type RiskAgentOptions, type RiskAgentThread } from './riskAgent'

export function listCodingThreads(): Promise<RiskAgentThread[]> {
  return apiFetch('/coding-agent/threads')
}

export function getCodingThread(id: string): Promise<RiskAgentThread> {
  return apiFetch(`/coding-agent/threads/${encodeURIComponent(id)}`)
}

export function deleteCodingThread(id: string): Promise<void> {
  return apiFetch(`/coding-agent/threads/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function getCodingHealth(): Promise<{ ok: boolean }> {
  return apiFetch('/coding-agent/health')
}

export function getCodingOptions(): Promise<RiskAgentOptions & { execution_backend: 'local' | 'opensandbox' }> {
  return apiFetch('/coding-agent/options')
}

export async function downloadCodingSnapshot(threadId: string): Promise<Blob> {
  const headers = authHeaders()
  ensureRequestId(headers)
  const response = await fetch(`${API_BASE}/coding-agent/threads/${encodeURIComponent(threadId)}/export`, { headers })
  rememberResponseRequestId(response)
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: unknown; extra?: { error_code?: string } }
    throw new ApiRequestError(formatErrorDetail(body.detail, response.status), response.status, body.extra?.error_code)
  }
  return response.blob()
}

export function getCodingProjects(): Promise<{ projects: string[] }> {
  return apiFetch('/coding-agent/projects')
}

export function streamCodingMessage(
  threadId: string | null,
  content: string,
  modelId: string,
  onEvent: (event: RiskAgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamAgentMessage('coding-agent', threadId, content, modelId, onEvent, signal)
}
