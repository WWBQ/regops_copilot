import { apiFetch } from './client'

export type SessionDocumentStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED'

export interface SessionCreateResponse {
  session_id: string
  expires_at: string | null
}

export interface SessionDocument {
  doc_id: string
  source_filename: string
  job_id: string | null
  status: SessionDocumentStatus
  page_count: number | null
  chunk_count: number | null
  error_message: string | null
  created_at?: string
  updated_at?: string
}

export interface SessionDocumentListResponse {
  session_id: string
  items: SessionDocument[]
}

export interface SessionDocumentUploadResponse {
  session_id: string
  doc_id: string
  job_id: string
  status: SessionDocumentStatus
  source_filename: string
  message: string
}

const SESSION_STORAGE_KEY = 'regops_chat_session_id'

export function getStoredSessionId(): string | null {
  return localStorage.getItem(SESSION_STORAGE_KEY)
}

export function storeSessionId(sessionId: string): void {
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId)
}

export function clearStoredSessionId(): void {
  localStorage.removeItem(SESSION_STORAGE_KEY)
}

export function createSession(): Promise<SessionCreateResponse> {
  return apiFetch('/sessions', { method: 'POST' })
}

async function sessionIsValid(sessionId: string): Promise<boolean> {
  try {
    await apiFetch(`/sessions/${sessionId}/documents`)
    return true
  } catch {
    return false
  }
}

export async function ensureSessionId(): Promise<string> {
  const existing = getStoredSessionId()
  if (existing && (await sessionIsValid(existing))) {
    return existing
  }
  try {
    const created = await createSession()
    storeSessionId(created.session_id)
    return created.session_id
  } catch (err) {
    if (existing) {
      return existing
    }
    throw err
  }
}

export async function startNewSession(): Promise<string> {
  clearStoredSessionId()
  const created = await createSession()
  storeSessionId(created.session_id)
  return created.session_id
}

export function listSessionDocuments(sessionId: string): Promise<SessionDocumentListResponse> {
  return apiFetch(`/sessions/${sessionId}/documents`)
}

export function getSessionDocument(sessionId: string, docId: string): Promise<SessionDocument> {
  return apiFetch(`/sessions/${sessionId}/documents/${docId}`)
}

export function uploadSessionDocument(
  sessionId: string,
  file: File,
): Promise<SessionDocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch(`/sessions/${sessionId}/documents`, {
    method: 'POST',
    body: form,
  })
}

export async function waitForDocumentReady(
  sessionId: string,
  docId: string,
  options?: { intervalMs?: number; timeoutMs?: number; onStatus?: (doc: SessionDocument) => void },
): Promise<SessionDocument> {
  const intervalMs = options?.intervalMs ?? 3000
  const timeoutMs = options?.timeoutMs ?? 30 * 60 * 1000
  const started = Date.now()

  for (;;) {
    const doc = await getSessionDocument(sessionId, docId)
    options?.onStatus?.(doc)
    if (doc.status === 'READY' || doc.status === 'FAILED') {
      return doc
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error('文档解析超时，请稍后重试')
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}
