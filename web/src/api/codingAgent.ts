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

export function getCodingOptions(): Promise<RiskAgentOptions & { execution_backend: 'opensandbox' }> {
  return apiFetch('/coding-agent/options')
}

export interface CodingSandboxResponse {
  thread: Pick<RiskAgentThread, 'id' | 'title' | 'status' | 'sandboxReady'>
  sandbox_created: boolean
  workspace_notice: string | null
}

export interface CodingUploadResponse {
  thread: CodingSandboxResponse['thread']
  file_count: number
  snapshot_saved: boolean
  message: string
  workspace_notice: string | null
}

export function prepareCodingSandbox(threadId: string | null): Promise<CodingSandboxResponse> {
  const path = threadId
    ? `/coding-agent/threads/${encodeURIComponent(threadId)}/sandbox`
    : '/coding-agent/threads/sandbox'
  return apiFetch(path, { method: 'POST' })
}

export function uploadCodingFile(threadId: string, file: File): Promise<CodingUploadResponse> {
  const body = new FormData()
  body.append('file', file, file.name)
  return apiFetch(`/coding-agent/threads/${encodeURIComponent(threadId)}/files`, { method: 'POST', body })
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

export function streamCodingMessage(
  threadId: string | null,
  content: string,
  modelId: string,
  onEvent: (event: RiskAgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamAgentMessage('coding-agent', threadId, content, modelId, onEvent, signal)
}
