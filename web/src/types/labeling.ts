export type UrlType = 'pdf' | 'html' | 'text'

export interface LabelTask {
  id: string
  name: string
  desc: string
  created_at: string
  count: number
  progress: number
  url_type: UrlType
  label_options: string[]
}

export interface LabelItem {
  index: number
  url: string
  type: UrlType
  text: string
  otext: string
  detailId: string
  info: unknown
  status: string
  notes: string
  taskId: string
  total?: number
  pdf_filename?: string
  download_msg?: string
  label_options?: string[]
}

export interface LabelItemList {
  task: LabelTask
  items: LabelItem[]
}

export interface SaveLabelResponse {
  ok: boolean
  saved: Record<string, unknown>
  progress: number
}
