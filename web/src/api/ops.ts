import { apiFetch } from './client'

export interface RagHitSnapshot {
  rank: number
  doc_id: string
  chunk_index: number
  page: number
  score: number
  vector_score: number | null
  keyword_score: number | null
  snippet: string
}

export interface RagTraceItem {
  id: number
  request_id: string | null
  session_id: string | null
  question: string
  outcome: string
  rag_used: boolean
  keyword_terms: string[]
  scoped_doc_ids: string[]
  vector_hit_count: number
  keyword_hit_count: number
  final_hit_count: number
  max_vector_score: number | null
  min_score_threshold: number | null
  total_rag_ms: number
  hits: RagHitSnapshot[]
  pipeline: Record<string, unknown>
  created_at: string
}

export interface RagTraceListResponse {
  total: number
  limit: number
  offset: number
  items: RagTraceItem[]
}

export function listRagTraces(params?: {
  limit?: number
  offset?: number
  outcome?: string
}): Promise<RagTraceListResponse> {
  const search = new URLSearchParams()
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  if (params?.outcome) search.set('outcome', params.outcome)
  const qs = search.toString()
  return apiFetch<RagTraceListResponse>(`/ops/rag-traces${qs ? `?${qs}` : ''}`)
}

export const OUTCOME_LABELS: Record<string, string> = {
  ok: '成功',
  no_intent: '无意图',
  no_docs: '无文档',
  low_score: '分数过低',
  pending_docs: '文档解析中',
}

export interface IngestCorpusDocument {
  doc_id: string
  company_code: string | null
  report_year: number | null
  source_filename: string
  page_count: number
  file_size_bytes: number
  content_hash: string
  ingest_status: string
  has_parse_artifact: boolean
  chunk_count: number
  updated_at: string | null
}

export interface IngestOverview {
  checked_at: string
  corpus: {
    documents: IngestCorpusDocument[]
    by_status: Record<string, number>
    total_pages: number
    total_chunks: number
    with_parse_artifact: number
  }
  jobs: {
    by_status: Record<string, number>
    total: number
    failed_24h: number
    pending: number
  }
  session_uploads: {
    by_status: Record<string, number>
    total: number
    pending: number
  }
}

export interface IngestJobItem {
  job_id: string
  target_type: string
  target_doc_id: string
  status: string
  error_message: string | null
  retry_count: number
  created_at: string | null
  updated_at: string | null
  finished_at: string | null
}

export interface SessionIngestDocument {
  session_id: string
  doc_id: string
  source_filename: string
  job_id: string | null
  status: string
  page_count: number | null
  chunk_count: number | null
  error_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface PaginatedResponse<T> {
  total: number
  limit: number
  offset: number
  items: T[]
}

export interface LogEventItem {
  id: string
  source: string
  level: string
  message: string
  detail: Record<string, unknown>
  occurred_at: string | null
}

export interface LogEventsResponse extends PaginatedResponse<LogEventItem> {
  summary: {
    by_level: Record<string, number>
    by_source: Record<string, number>
  }
}

export function getIngestOverview(): Promise<IngestOverview> {
  return apiFetch<IngestOverview>('/ops/ingest/overview')
}

export function listIngestJobs(params?: {
  limit?: number
  offset?: number
  status?: string
  target_type?: string
}): Promise<PaginatedResponse<IngestJobItem>> {
  const search = new URLSearchParams()
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  if (params?.status) search.set('status', params.status)
  if (params?.target_type) search.set('target_type', params.target_type)
  const qs = search.toString()
  return apiFetch<PaginatedResponse<IngestJobItem>>(`/ops/ingest/jobs${qs ? `?${qs}` : ''}`)
}

export function listSessionIngestDocuments(params?: {
  limit?: number
  offset?: number
  status?: string
}): Promise<PaginatedResponse<SessionIngestDocument>> {
  const search = new URLSearchParams()
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  if (params?.status) search.set('status', params.status)
  const qs = search.toString()
  return apiFetch<PaginatedResponse<SessionIngestDocument>>(
    `/ops/ingest/session-documents${qs ? `?${qs}` : ''}`,
  )
}

export function listLogEvents(params?: {
  limit?: number
  offset?: number
  source?: string
  level?: string
}): Promise<LogEventsResponse> {
  const search = new URLSearchParams()
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  if (params?.source) search.set('source', params.source)
  if (params?.level) search.set('level', params.level)
  const qs = search.toString()
  return apiFetch<LogEventsResponse>(`/ops/logs/events${qs ? `?${qs}` : ''}`)
}

export const INGEST_STATUS_LABELS: Record<string, string> = {
  uploaded: '已上传',
  processing: '处理中',
  ready: '就绪',
  failed: '失败',
  archived: '已归档',
  PENDING: '待处理',
  PARSING: '解析中',
  CLEANING: '清洗中',
  EXTRACTING: '抽取中',
  CHUNKING: '分块中',
  EMBEDDING: '向量化中',
  DONE: '完成',
  FAILED: '失败',
  PROCESSING: '处理中',
  READY: '就绪',
}

export const LOG_SOURCE_LABELS: Record<string, string> = {
  ingest: '入库任务',
  session: '会话上传',
  rag: 'RAG 检索',
}

export const LOG_LEVEL_LABELS: Record<string, string> = {
  error: '错误',
  warn: '警告',
  info: '信息',
}
