/** 应用内 PDF 预览地址（经 BFF inline 流式返回，不触发下载） */
export function documentViewerPage(docId: string, page?: number): string {
  const params = new URLSearchParams()
  if (page != null && page > 0) {
    params.set('page', String(page))
  }
  const query = params.toString()
  return `/documents/${encodeURIComponent(docId)}/view${query ? `?${query}` : ''}`
}

export function documentContentUrl(docId: string, page?: number): string {
  const base = `/api/documents/${encodeURIComponent(docId)}/content`
  if (page != null && page > 0) {
    return `${base}#page=${page}`
  }
  return base
}
