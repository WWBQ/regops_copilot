import type { Citation } from '../types/chat'
import { renderMarkdown } from './markdown'

const CITE_FOOTER_RE = /\n*出处：(?:\[(?:片段)?\d{1,2}\])+\s*$/u

function citeMarkerRe(): RegExp {
  return /\[(?:片段)?(\d{1,2})\]/g
}

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
  if (citation.kind === 'facts') {
    return docTitle
  }
  return `${docTitle} · 第 ${citation.page} 页`
}

function stripCiteFooter(text: string): string {
  return text.replace(CITE_FOOTER_RE, '').replace(/\s+$/u, '')
}

function groupedDecimal(plain: string): string {
  const negative = plain.startsWith('-')
  const raw = negative ? plain.slice(1) : plain
  const [integer, fraction] = raw.split('.')
  const grouped = Number(integer).toLocaleString('en-US')
  const body = fraction != null && fraction !== '' ? `${grouped}.${fraction}` : grouped
  return negative ? `-${body}` : body
}

function amountNeedles(amount: string): string[] {
  const compact = amount.replace(/(\.\d*?)0+$/u, '$1').replace(/\.$/u, '')
  const grouped = groupedDecimal(compact)
  const needles: string[] = []
  if (grouped !== compact) {
    needles.push(grouped)
  }
  const abs = Math.abs(Number(compact))
  if (abs >= 100) {
    needles.push(compact)
  }
  const yi = Number(compact) / 1e8
  if (Number.isFinite(yi) && Math.abs(yi) >= 0.01) {
    const yiText = yi.toFixed(2)
    const yiGrouped = groupedDecimal(yiText)
    for (const item of [yiGrouped, yiText]) {
      needles.push(`${item} 亿元`, `${item}亿元`, item)
    }
  } else if (abs >= 1) {
    needles.push(compact)
  }
  return needles
}

function citeNeedles(cite: Citation): string[] {
  if (cite.kind === 'facts') {
    const token = cite.snippet?.trim().split(/\s+/u).pop() ?? ''
    if (!/^-?\d+(?:\.\d+)?$/u.test(token)) {
      return []
    }
    return amountNeedles(token)
  }
  const needles: string[] = []
  if (cite.page) {
    needles.push(`第${cite.page}页`, `第 ${cite.page} 页`)
  }
  for (const token of cite.snippet?.match(/\d{1,3}(?:,\d{3})+(?:\.\d+)?/gu) ?? []) {
    needles.push(token)
  }
  return needles
}

function alreadyMarked(text: string, at: number): boolean {
  return /^\s*\[(?:片段)?\d{1,2}\]/u.test(text.slice(at, at + 12))
}

function insertAfter(text: string, needle: string, mark: string): string | null {
  let start = 0
  while (start <= text.length) {
    const index = text.indexOf(needle, start)
    if (index < 0) {
      return null
    }
    const end = index + needle.length
    if (!alreadyMarked(text, end)) {
      return text.slice(0, end) + mark + text.slice(end)
    }
    start = end
  }
  return null
}

function placeMark(text: string, mark: string, cite: Citation): string | null {
  if (cite.kind !== 'facts' && cite.doc_id && cite.page) {
    const escaped = cite.doc_id.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')
    const paren = new RegExp(`[（(][^）)]*${escaped}[^）)]*第\\s*${cite.page}\\s*页[^）)]*[）)]`, 'u')
    const match = paren.exec(text)
    if (match?.index != null) {
      return text.slice(0, match.index) + mark + text.slice(match.index + match[0].length)
    }
  }
  for (const needle of citeNeedles(cite)) {
    const placed = insertAfter(text, needle, mark)
    if (placed != null) {
      return placed
    }
  }
  return null
}

function compactMarks(text: string, citations: Citation[]): { content: string; citations: Citation[] } {
  const remap = new Map<number, number>()
  const kept: Citation[] = []
  const content = text.replace(citeMarkerRe(), (all, raw: string) => {
    const old = Number.parseInt(raw, 10)
    const index = old - 1
    if (index < 0 || index >= citations.length) {
      return all
    }
    let next = remap.get(old)
    if (!next) {
      next = kept.length + 1
      remap.set(old, next)
      kept.push(citations[index])
    }
    return `[${next}]`
  })
  return { content, citations: kept }
}

/** 把对得上的出处嵌进正文；对不上的丢掉，不堆文末列表。 */
export function attachCitationMarks(
  content: string,
  citations: Citation[] = [],
): { content: string; citations: Citation[] } {
  let text = stripCiteFooter(content)
  if (!citations.length) {
    return { content: text, citations: [] }
  }
  const used = new Set<number>()
  for (const match of text.matchAll(citeMarkerRe())) {
    const index = Number.parseInt(match[1], 10) - 1
    if (index >= 0 && index < citations.length) {
      used.add(index)
    }
  }
  for (let index = 0; index < citations.length; index += 1) {
    if (used.has(index)) {
      continue
    }
    const placed = placeMark(text, `[${index + 1}]`, citations[index])
    if (placed == null) {
      continue
    }
    text = placed
    used.add(index)
  }
  return compactMarks(text, citations)
}

/** 将正文中的 [1] 角标替换为可点击的行内引用标记 */
export function injectInlineCitationMarkers(html: string, citations: Citation[]): string {
  if (!citations.length) {
    return html
  }
  return html.replace(citeMarkerRe(), (match, rawIndex: string) => {
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
  const bound = attachCitationMarks(content, citations ?? [])
  const html = renderMarkdown(bound.content)
  if (!bound.citations.length) {
    return html
  }
  return injectInlineCitationMarkers(html, bound.citations)
}

export function citationAt(citations: Citation[] | undefined, index: number): Citation | null {
  if (!citations?.length || index < 0 || index >= citations.length) {
    return null
  }
  return citations[index]
}
