import { API_BASE, apiFetch } from './client'
import type { LabelItem, LabelItemList, LabelTask, SaveLabelResponse } from '../types/labeling'

export function listLabelTasks(): Promise<LabelTask[]> {
  return apiFetch('/labeling/tasks')
}

export function createLabelTask(form: FormData): Promise<LabelTask> {
  return apiFetch('/labeling/tasks', { method: 'POST', body: form })
}

export function getLabelTask(taskId: string): Promise<LabelItemList> {
  return apiFetch(`/labeling/tasks/${taskId}`)
}

export function getLabelItem(taskId: string, idx: number): Promise<LabelItem> {
  return apiFetch(`/labeling/tasks/${taskId}/items/${idx}`)
}

export function saveLabelItem(
  taskId: string,
  idx: number,
  body: Record<string, unknown>,
): Promise<SaveLabelResponse> {
  return apiFetch(`/labeling/tasks/${taskId}/items/${idx}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function pdfUrl(taskId: string, filename: string): string {
  return `${API_BASE}/labeling/tasks/${taskId}/pdf/${encodeURIComponent(filename)}`
}

export function htmlProxyUrl(taskId: string, idx: number): string {
  return `${API_BASE}/labeling/tasks/${taskId}/html/${idx}`
}

export async function downloadLabelTemplate(): Promise<void> {
  const response = await fetch(`${API_BASE}/labeling/template`)
  if (!response.ok) {
    throw new Error(`下载模板失败 (${response.status})`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'labeling_template.xlsx'
  link.click()
  URL.revokeObjectURL(url)
}

export async function downloadLabelExport(taskId: string, name: string): Promise<void> {
  const response = await fetch(`${API_BASE}/labeling/tasks/${taskId}/export`)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = (body as { detail?: string }).detail
    throw new Error(detail || `导出失败 (${response.status})`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${name}_report.xlsx`
  link.click()
  URL.revokeObjectURL(url)
}
