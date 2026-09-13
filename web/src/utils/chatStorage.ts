import type { ChatMessage, PendingAsknum } from '../types/chat'

const MESSAGES_KEY_PREFIX = 'regops_chat_messages:'
const MAX_MESSAGES = 200

function storageKey(sessionId: string): string {
  return `${MESSAGES_KEY_PREFIX}${sessionId}`
}

export function loadChatMessages(sessionId: string): ChatMessage[] | null {
  try {
    const raw = localStorage.getItem(storageKey(sessionId))
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return null
    }
    return parsed as ChatMessage[]
  } catch {
    return null
  }
}

export function saveChatMessages(sessionId: string, messages: ChatMessage[]): void {
  try {
    const trimmed = messages.slice(-MAX_MESSAGES).map((item) => {
      const { streaming: _streaming, statusText: _statusText, ...rest } = item
      return rest
    })
    localStorage.setItem(storageKey(sessionId), JSON.stringify(trimmed))
  } catch {
    // localStorage 满或不可用时静默跳过
  }
}

const THREAD_KEY_PREFIX = 'regops_workflow_thread:'

export function loadWorkflowThreadId(sessionId: string): string | null {
  try {
    return localStorage.getItem(`${THREAD_KEY_PREFIX}${sessionId}`)
  } catch {
    return null
  }
}

export function saveWorkflowThreadId(sessionId: string, threadId: string | null): void {
  try {
    const key = `${THREAD_KEY_PREFIX}${sessionId}`
    if (!threadId) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, threadId)
  } catch {
    // ignore
  }
}

const PENDING_KEY_PREFIX = 'regops_asknum_pending:'

export function loadPendingAsknum(sessionId: string): PendingAsknum | null {
  try {
    const raw = localStorage.getItem(`${PENDING_KEY_PREFIX}${sessionId}`)
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as PendingAsknum
  } catch {
    return null
  }
}

export function savePendingAsknum(sessionId: string, pending: PendingAsknum | null): void {
  try {
    const key = `${PENDING_KEY_PREFIX}${sessionId}`
    if (!pending || (pending.missing && pending.missing.length === 0)) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, JSON.stringify(pending))
  } catch {
    // ignore
  }
}

export function clearChatMessages(sessionId: string): void {
  localStorage.removeItem(storageKey(sessionId))
  localStorage.removeItem(`${PENDING_KEY_PREFIX}${sessionId}`)
}

export function createWelcomeMessage(): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content:
      '你好，我是 RegOps Copilot。营收/净利润走财务事实库；风险/制度检索年报并附页码。两家对比+结论走固定工作流，出结论前会暂停确认。经营概况、研发/毛利率/分红、待复核数字追问会让模型自选只读工具。也可 📎 上传仅本会话有效的 PDF。',
  }
}
