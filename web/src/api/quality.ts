import { apiFetch } from './client'

export interface QualityRuleResult {
  rule_id: string
  name: string
  passed: boolean
  message: string
  concepts: string[]
  left: string | null
  right: string | null
}

export interface QualityCompanyGate {
  company_code: string
  company_name: string
  doc_id: string
  period: string
  scope: string
  fact_count: number
  auto_accepted: number
  human_review: number
  rejected?: number
  missing_critical: string[]
  g1: { passed: boolean; conflicts: Array<{ fact_key: string; reason?: string | null }> }
  g2: { passed: boolean; rules: QualityRuleResult[] }
  g3: { passed: boolean; policy: string; failed: Array<{ fact_key: string; reason: string }> }
}

export interface QualityGatesResponse {
  checked_at: string
  source: string
  summary: {
    companies: number
    facts: number
    auto_accepted: number
    human_review: number
    g2_all_passed: boolean
    g3_all_passed: boolean
    missing_critical_companies: number
  }
  companies: QualityCompanyGate[]
  f10_ready?: boolean
  f10_root?: string
}

export interface FinMetricItem {
  id: number
  company_code: string | null
  company_name?: string
  doc_id: string
  source_type: string
  fact_key: string
  concept: string
  period: string
  scope: string
  currency: string
  statement: string
  value_yuan: string | null
  value_display?: string
  unit_raw: string | null
  raw_name: string | null
  raw_value: string | null
  page_no: number | null
  parser: string | null
  status: string
  review_reason: string | null
  xbrl_tag: string | null
  content_hash: string | null
  updated_at: string | null
}

export interface FinMetricListResponse {
  total: number
  limit: number
  offset: number
  items: FinMetricItem[]
}

export function fetchQualityGates(): Promise<QualityGatesResponse> {
  return apiFetch<QualityGatesResponse>('/ops/quality/gates')
}

export function listFinMetrics(params?: {
  limit?: number
  offset?: number
  company_code?: string
  status?: string
  statement?: string
  concept?: string
  doc_id?: string
}): Promise<FinMetricListResponse> {
  const search = new URLSearchParams()
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  if (params?.company_code) search.set('company_code', params.company_code)
  if (params?.status) search.set('status', params.status)
  if (params?.statement) search.set('statement', params.statement)
  if (params?.concept) search.set('concept', params.concept)
  if (params?.doc_id) search.set('doc_id', params.doc_id)
  const qs = search.toString()
  return apiFetch<FinMetricListResponse>(`/ops/quality/facts${qs ? `?${qs}` : ''}`)
}

export function ingestFinMetrics(body?: {
  codes?: string[]
  year?: number
  dry_run?: boolean
}): Promise<{ summary: QualityGatesResponse['summary']; missing_dirs?: string[] }> {
  return apiFetch('/ops/quality/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
}

export const STATEMENT_LABELS: Record<string, string> = {
  balance_sheet: '资产负债表',
  income: '利润表',
  cash_flow: '现金流量表',
}

export const METRIC_STATUS_LABELS: Record<string, string> = {
  auto_accepted: '自动通过',
  human_review: '人工复核',
  rejected: '已拒绝',
}
