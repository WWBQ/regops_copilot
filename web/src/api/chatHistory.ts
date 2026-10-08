import { apiFetch } from './client'
import type { ChatMessage } from '../types/chat'
import type { ChatSessionMeta } from '../composables/chatBridge'

export interface StoredChatSession {
  sessionId: string
  title: string
  customTitle: boolean
  updatedAt: string
}

export interface StoredChatDetail extends StoredChatSession {
  messages: ChatMessage[]
}

export interface ChatSnapshot {
  sessionId: string
  title: string
  customTitle: boolean
  updatedAt?: string
  messages: ChatMessage[]
}

export function listStoredChats(): Promise<StoredChatSession[]> {
  return apiFetch('/chat-history')
}

export function getStoredChat(sessionId: string): Promise<StoredChatDetail> {
  return apiFetch(`/chat-history/${encodeURIComponent(sessionId)}`)
}

export function saveStoredChat(snapshot: ChatSnapshot): Promise<StoredChatSession> {
  return apiFetch(`/chat-history/${encodeURIComponent(snapshot.sessionId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snapshot),
  })
}

export function importLocalChats(snapshots: ChatSnapshot[]): Promise<StoredChatSession[]> {
  return apiFetch('/chat-history/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(snapshots),
  })
}

export function deleteStoredChat(sessionId: string): Promise<void> {
  return apiFetch(`/chat-history/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

export function renameStoredChat(sessionId: string, title: string): Promise<StoredChatSession> {
  return apiFetch(`/chat-history/${encodeURIComponent(sessionId)}/title`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export function toSessionMeta(item: StoredChatSession): ChatSessionMeta {
  return {
    sessionId: item.sessionId,
    title: item.title,
    customTitle: item.customTitle,
    updatedAt: item.updatedAt,
  }
}
