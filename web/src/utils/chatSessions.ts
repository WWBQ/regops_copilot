import type { ChatSessionMeta } from '../composables/chatBridge'
import type { ChatMessage } from '../types/chat'
import { loadChatMessages } from './chatStorage'

const SESSION_LIST_KEY = 'regops_chat_session_list'
const MESSAGES_KEY_PREFIX = 'regops_chat_messages:'
const MAX_SESSIONS = 30

export function defaultNewChatTitle(at?: string | Date): string {
  const date = at ? new Date(at) : new Date()
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  return `新对话 · ${time}`
}

export function listChatSessions(): ChatSessionMeta[] {
  try {
    const raw = localStorage.getItem(SESSION_LIST_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed as ChatSessionMeta[]
  } catch {
    return []
  }
}

export function saveChatSessions(sessions: ChatSessionMeta[]): void {
  try {
    localStorage.setItem(SESSION_LIST_KEY, JSON.stringify(sessions.slice(0, MAX_SESSIONS)))
  } catch {
    // ignore
  }
}

export function upsertChatSession(
  meta: ChatSessionMeta,
  options?: { moveToFront?: boolean },
): ChatSessionMeta[] {
  const sessions = listChatSessions()
  const index = sessions.findIndex((item) => item.sessionId === meta.sessionId)
  if (index >= 0) {
    if (options?.moveToFront) {
      sessions.splice(index, 1)
      sessions.unshift(meta)
    } else {
      sessions[index] = meta
    }
  } else {
    sessions.unshift(meta)
  }
  saveChatSessions(sessions)
  return listChatSessions()
}

export function removeChatSession(sessionId: string): ChatSessionMeta[] {
  const sessions = listChatSessions().filter((item) => item.sessionId !== sessionId)
  saveChatSessions(sessions)
  return sessions
}

export function renameChatSession(sessionId: string, title: string): ChatSessionMeta[] {
  const trimmed = title.trim()
  if (!trimmed) {
    return listChatSessions()
  }
  const sessions = listChatSessions()
  const index = sessions.findIndex((item) => item.sessionId === sessionId)
  if (index < 0) {
    return sessions
  }
  sessions[index] = {
    ...sessions[index],
    title: trimmed.length > 48 ? `${trimmed.slice(0, 48)}…` : trimmed,
    customTitle: true,
  }
  saveChatSessions(sessions)
  return listChatSessions()
}

export function deriveSessionTitle(messages: ChatMessage[], fallbackAt?: string): string {
  const firstUser = messages.find((item) => item.role === 'user' && item.content.trim())
  if (!firstUser) {
    return defaultNewChatTitle(fallbackAt)
  }
  const text = firstUser.content.replace(/^上传文档：/, '').trim()
  return text.length > 24 ? `${text.slice(0, 24)}…` : text
}

function hasUserMessage(messages: ChatMessage[]): boolean {
  return messages.some((item) => item.role === 'user' && item.content.trim())
}

/** 从 localStorage 消息键与已有列表合并，恢复侧边栏对话记录 */
export function rebuildChatSessionsFromStorage(): ChatSessionMeta[] {
  const map = new Map<string, ChatSessionMeta>()
  for (const item of listChatSessions()) {
    map.set(item.sessionId, item)
  }

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index)
    if (!key?.startsWith(MESSAGES_KEY_PREFIX)) {
      continue
    }
    const sessionId = key.slice(MESSAGES_KEY_PREFIX.length)
    if (!sessionId) {
      continue
    }
    const messages = loadChatMessages(sessionId)
    if (!messages?.length) {
      continue
    }
    const existing = map.get(sessionId)
    const updatedAt = existing?.updatedAt ?? new Date().toISOString()
    map.set(sessionId, {
      sessionId,
      title: existing?.customTitle
        ? existing.title
        : hasUserMessage(messages)
          ? deriveSessionTitle(messages)
          : (existing?.title ?? defaultNewChatTitle(updatedAt)),
      updatedAt,
      customTitle: existing?.customTitle,
    })
  }

  const merged = Array.from(map.values())
  saveChatSessions(merged)
  return merged
}
