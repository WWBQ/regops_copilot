import { apiFetch } from './client'

export interface AnnualReport {
  doc_id: string
  company_code: string
  report_year: number
  source_filename: string
  page_count: number | null
  size: number
  ingest_status: string
  updated_at: string
  /** 私有对象存储的短期预签名链接，生成后 5 分钟失效。 */
  object_url: string | null
}

export function listAnnualReports(): Promise<{ items: AnnualReport[] }> {
  return apiFetch('/documents/reports')
}
