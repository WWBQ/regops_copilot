import type { ChatMessage } from '../types/chat'

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
    const trimmed = messages.slice(-MAX_MESSAGES)
    localStorage.setItem(storageKey(sessionId), JSON.stringify(trimmed))
  } catch {
    // localStorage 满或不可用时静默跳过
  }
}

export function clearChatMessages(sessionId: string): void {
  localStorage.removeItem(storageKey(sessionId))
}

export function createWelcomeMessage(): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    content:
      '你好，我是 RegOps Copilot。营收/净利润等直读指标走财务事实库，风险/制度等叙述检索年报并附页码。复杂对比以后仍在本对话里拆步，不必换页面。也可 📎 上传仅本会话有效的 PDF。',
  }
}
