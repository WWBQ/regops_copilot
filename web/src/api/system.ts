import { apiFetch } from './client'
import { getHealth } from './chat'

export interface ServiceHealth {
  status: string
  latency_ms?: number | null
  error?: string | null
  service?: string
  installed?: boolean
}

export interface CorpusDocument {
  doc_id: string
  company_code: string | null
  report_year: number | null
  page_count: number
  chunk_count: number
  ingest_status: string
  updated_at: string | null
}

export interface IngestJobRow {
  job_id: string
  target_type: string
  target_doc_id: string
  status: string
  error_message: string | null
  created_at: string | null
  updated_at: string | null
  finished_at: string | null
}

export interface SystemOverview {
  checked_at: string
  services: {
    python_ai: ServiceHealth
    postgresql: ServiceHealth
    pgvector: ServiceHealth
  }
  corpus: {
    documents: CorpusDocument[]
    ready_count: number
    total_chunks: number
    total_pages: number
  }
  ingest_jobs: IngestJobRow[]
  sessions: {
    session_count: number
    pending_documents: number
  }
  rag_traces: {
    total: number
    last_24h: number
    by_outcome: Record<string, number>
  }
  eval: {
    task_count: number
  }
  config: {
    default_model: string
    embedding_model: string
    rag_top_k: number
    rag_rerank_enabled: boolean
    rag_trace_enabled: boolean
  }
}

export interface BffHealth {
  status: string
  service: string
  pythonAi?: ServiceHealth & Record<string, unknown>
}

export function getSystemOverview(): Promise<SystemOverview> {
  return apiFetch<SystemOverview>('/ops/system/overview')
}

export async function getBffHealth(): Promise<BffHealth> {
  return apiFetch<BffHealth>('/health')
}

export { getHealth }
