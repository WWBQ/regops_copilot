import type { ChatMessage, Citation, RiskAuditResult } from '../../types/chat'

export interface AgentTextPart {
  id: string
  text: string
  citations?: Citation[]
  riskResult?: RiskAuditResult | null
  citationConflicts?: number[]
}

interface HistoryMessage {
  id: string
  author: string
  chunks: Array<{ kind: string; text?: string }>
  citations?: Citation[]
  risk_result?: RiskAuditResult | null
  citation_conflicts?: number[]
}

/** 一轮用户提问只对应一条回答；此前的 assistant 文本是执行阶段。 */
export function groupRiskAgentHistory(history: HistoryMessage[]): ChatMessage[] {
  const result: ChatMessage[] = []
  let assistantParts: AgentTextPart[] = []

  function flushAssistant() {
    if (!assistantParts.length) return
    const last = assistantParts[assistantParts.length - 1]
    result.push({
      id: last.id,
      role: 'assistant',
      route: 'risk_agent',
      content: last.text,
      stages: assistantParts.slice(0, -1).map((part) => part.text),
      citations: [...assistantParts].reverse().find((part) => part.citations?.length)?.citations,
      riskResult: [...assistantParts].reverse().find((part) => part.riskResult)?.riskResult,
      citationConflicts: [...assistantParts].reverse().find((part) => part.citationConflicts?.length)?.citationConflicts,
    })
    assistantParts = []
  }

  for (const message of history) {
    if (message.author !== 'user' && message.author !== 'agent') continue
    const content = message.chunks
      .filter((chunk) => chunk.kind === 'text')
      .map((chunk) => chunk.text ?? '')
      .join('')
      .trim()
    if (!content) continue
    if (message.author === 'user') {
      flushAssistant()
      result.push({ id: message.id, role: 'user', content })
    } else {
      assistantParts.push({
        id: message.id,
        text: content,
        citations: message.citations,
        riskResult: message.risk_result,
        citationConflicts: message.citation_conflicts,
      })
    }
  }
  flushAssistant()
  return result
}

/** text_delta 的 replace 是累计全文，append 才是增量。 */
export function updateAgentTextPart(
  parts: AgentTextPart[],
  id: string,
  text: string,
  mode: string,
): AgentTextPart[] {
  const index = parts.findIndex((part) => part.id === id)
  if (index < 0) return [...parts, { id, text }]
  return parts.map((part, at) => at === index
    ? { id, text: mode === 'replace' ? text : part.text + text }
    : part)
}

export function presentAgentRun(parts: AgentTextPart[], finalAnswer?: string): {
  content: string
  stages: string[]
  stageText: string
} {
  const texts = parts.map((part) => part.text.trim()).filter(Boolean)
  if (finalAnswer === undefined) {
    return { content: '', stages: texts.slice(0, -1), stageText: texts.at(-1) ?? '' }
  }

  const answer = finalAnswer.trim() || texts.at(-1) || ''
  // 正常情况下最后一段流式文本就是最终回答。若模型把答案拆成多个文本块，
  // 从尾部找能拼出完整答案的块，避免把答案前半段错归为“过程”。
  let stageCount = Math.max(0, texts.length - 1)
  for (let index = 0; index < texts.length; index += 1) {
    if (texts.slice(index).join('') === answer) {
      stageCount = index
      break
    }
  }
  return { content: answer, stages: texts.slice(0, stageCount), stageText: '' }
}
