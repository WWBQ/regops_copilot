const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'
const TOKEN_KEY = 'regops_jwt'

let lastRequestId: string | null = null

export function getLastRequestId(): string | null {
  return lastRequestId
}

export function newRequestId(): string {
  const id =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
  lastRequestId = id
  return id
}

export function rememberResponseRequestId(response: Response): string | null {
  const echoed = response.headers.get('X-Request-ID')
  if (echoed) {
    lastRequestId = echoed
    return echoed
  }
  return lastRequestId
}

export function ensureRequestId(headers: Headers): string {
  const existing = headers.get('X-Request-ID')?.trim()
  if (existing) {
    lastRequestId = existing
    return existing
  }
  const id = newRequestId()
  headers.set('X-Request-ID', id)
  return id
}

export function getAuthToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  } catch {
    /* ignore */
  }
}

export function authHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra)
  const token = getAuthToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return headers
}

export function formatErrorDetail(detail: unknown, status: number): string {
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: string }).msg)
        }
        return JSON.stringify(item)
      })
      .join('；')
  }
  return `请求失败 (${status})`
}

export class ApiRequestError extends Error {
  status: number
  errorCode?: string
  requestId?: string

  constructor(message: string, status: number, errorCode?: string, requestId?: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.errorCode = errorCode
    this.requestId = requestId
  }
}

type ErrorBody = {
  detail?: unknown
  extra?: { error_code?: string; request_id?: string }
}

function requestIdFrom(response: Response, body: ErrorBody): string | undefined {
  rememberResponseRequestId(response)
  return body.extra?.request_id ?? response.headers.get('X-Request-ID') ?? lastRequestId ?? undefined
}

export function formatUserFacingError(err: unknown): string {
  if (err instanceof ApiRequestError) {
    const rid = err.requestId ? ` 关联 ID：${err.requestId}` : ''
    if (err.errorCode === 'upstream_down' || err.status === 502) {
      return `问答服务暂时连不上。合规复核和审计还可以用。${rid}`.trim()
    }
    if (err.errorCode === 'upstream_timeout' || err.status === 504) {
      return `问答超时，可点停止后重试。${rid}`.trim()
    }
    return `${err.message}${rid}`
  }
  if (err instanceof Error) {
    return err.message
  }
  return '请求失败'
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = authHeaders(init?.headers)
  ensureRequestId(headers)
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  rememberResponseRequestId(response)
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorBody
    throw new ApiRequestError(
      formatErrorDetail(body.detail, response.status),
      response.status,
      body.extra?.error_code,
      requestIdFrom(response, body),
    )
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export { API_BASE, TOKEN_KEY }
