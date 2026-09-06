import { apiFetch } from './client'

export interface EvalTask {
  id: string
  name: string
  description: string
  golden_file: string
  golden_version: string | null
  item_count: number
  metrics: string[]
  runner: string
  builtin?: boolean
}

export interface GoldenItemPreview {
  id: string
  category?: string | null
  question: string
}

export interface GoldenSetPreview {
  filename: string
  version: string | null
  item_count: number
  categories: string[]
  items: GoldenItemPreview[]
}

export interface EvalProgress {
  done: number
  total: number
  current_id: string | null
}

export interface EvalRunSummary {
  total?: number
  passed?: number
  failed?: number
  refused?: number
  accuracy?: number
  refuse_rate?: number
  number_error_rate?: number
  latency_p50_ms?: number
  model?: string
  count?: number
  recall_at_k?: number
  mrr?: number
  by_category?: Record<
    string,
    {
      recall_at_k?: number
      mrr?: number
      count?: number
      total?: number
      passed?: number
      refused?: number
      accuracy?: number
    }
  >
  // compliance_schema
  valid_total?: number
  invalid_total?: number
  false_accept?: number
  false_accept_rate?: number
  false_reject?: number
  false_reject_rate?: number
  rule_hit_rate?: number
  strict_pass_rate?: number
  by_rule?: Array<{ rule: string | null; total: number; passed: number; failed: number }>
}

export interface EvalRunItem {
  run_id: string
  task_id: string
  status: 'running' | 'completed' | 'failed'
  started_at: string | null
  finished_at: string | null
  progress: EvalProgress
  params: Record<string, unknown>
  error: string | null
  summary: EvalRunSummary | null
  report?: EvalReport
}

export interface EvalReport {
  task_id: string
  generated_at: string
  golden_version?: string
  summary: EvalRunSummary
  results: Record<string, unknown>[]
}

export function listEvalTasks(): Promise<{ items: EvalTask[] }> {
  return apiFetch<{ items: EvalTask[] }>('/ops/eval/tasks')
}

export function listGoldenSets(): Promise<{ items: GoldenSetOption[]; runners: string[] }> {
  return apiFetch<{ items: GoldenSetOption[]; runners: string[] }>('/ops/eval/golden-sets')
}

export function getGoldenSet(filename: string): Promise<GoldenSetPreview> {
  return apiFetch<GoldenSetPreview>(`/ops/eval/golden-sets/${encodeURIComponent(filename)}`)
}

export function uploadGoldenSet(body: {
  filename: string
  content: Record<string, unknown>
  runner?: string
}): Promise<{ filename: string; item_count: number; version?: string }> {
  return apiFetch('/ops/eval/golden-sets/upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function createEvalTask(body: {
  id: string
  name: string
  description?: string
  golden_file: string
  runner: string
}): Promise<EvalTask> {
  return apiFetch<EvalTask>('/ops/eval/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteEvalTask(taskId: string): Promise<{ status: string; task_id: string }> {
  return apiFetch<{ status: string; task_id: string }>(
    `/ops/eval/tasks/${encodeURIComponent(taskId)}`,
    { method: 'DELETE' },
  )
}

export function listEvalRuns(taskId?: string): Promise<{ items: EvalRunItem[]; total: number }> {
  const qs = taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''
  return apiFetch<{ items: EvalRunItem[]; total: number }>(`/ops/eval/runs${qs}`)
}

export function getEvalRun(runId: string, includeReport = true): Promise<EvalRunItem> {
  return apiFetch<EvalRunItem>(
    `/ops/eval/runs/${encodeURIComponent(runId)}?include_report=${includeReport}`,
  )
}

export function deleteEvalRun(runId: string): Promise<{ status: string; run_id: string }> {
  return apiFetch<{ status: string; run_id: string }>(
    `/ops/eval/runs/${encodeURIComponent(runId)}`,
    { method: 'DELETE' },
  )
}

export function startEvalRun(body: {
  task_id: string
  limit?: number
  category?: string
  categories?: string[]
  item_ids?: string[]
  top_k?: number
  model?: string
  temperature?: number
}): Promise<EvalRunItem> {
  return apiFetch<EvalRunItem>('/ops/eval/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export const EVAL_STATUS_LABELS: Record<string, string> = {
  running: '运行中',
  completed: '已完成',
  failed: '失败',
}

export const RUNNER_LABELS: Record<string, string> = {
  w1_chat: 'W1 聊天（/chat）',
  rag_retrieval: 'RAG 检索（page Recall@k）',
  compliance_schema: '合规结论 Schema 校验（误放行率）',
  w4_asknum: 'W4 问数（受控 lookup）',
}
