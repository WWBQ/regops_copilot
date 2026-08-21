const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

function formatErrorDetail(detail: unknown, status: number): string {
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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(formatErrorDetail((body as { detail?: unknown }).detail, response.status))
  }
  return response.json() as Promise<T>
}

export { API_BASE }
