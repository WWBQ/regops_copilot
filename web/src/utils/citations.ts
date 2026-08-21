import type { Citation } from '../types/chat'
import { renderMarkdown } from './markdown'

const CITE_MARKER_RE = /\[(\d{1,2})\]/g

function escapeAttr(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/** 引用标记 hover 提示：文档标题 + 页码 */
export function citationHoverLabel(citation: Citation): string {
  const docTitle = citation.title?.trim() || citation.doc_id
  return `${docTitle} · 第 ${citation.page} 页`
}

/** 将正文中的 [1] 角标替换为可点击的行内引用标记 */
export function injectInlineCitationMarkers(html: string, citations: Citation[]): string {
  if (!citations.length) {
    return html
  }
  return html.replace(CITE_MARKER_RE, (match, rawIndex: string) => {
    const index = Number.parseInt(rawIndex, 10) - 1
    if (Number.isNaN(index) || index < 0 || index >= citations.length) {
      return match
    }
    const citation = citations[index]
    const label = rawIndex
    const hover = escapeAttr(citationHoverLabel(citation))
    return (
      `<button type="button" class="cite-mark" data-cite-index="${index}" ` +
      `aria-label="引用 ${label}，${citationHoverLabel(citation)}" title="${hover}">${label}</button>`
    )
  })
}

export function renderAssistantMarkdown(content: string, citations?: Citation[]): string {
  const html = renderMarkdown(content)
  if (!citations?.length) {
    return html
  }
  return injectInlineCitationMarkers(html, citations)
}

export function citationAt(citations: Citation[] | undefined, index: number): Citation | null {
  if (!citations?.length || index < 0 || index >= citations.length) {
    return null
  }
  return citations[index]
}
