import type { InjectionKey, Ref } from 'vue'

export interface ChatSessionMeta {
  sessionId: string
  title: string
  updatedAt: string
  /** 用户手动重命名后，不再被首条消息自动覆盖标题 */
  customTitle?: boolean
}

export interface ChatBridge {
  ready: boolean
  busy: boolean
  activeSessionId: string
  sessions: ChatSessionMeta[]
  newChat: () => void | Promise<void>
  switchSession: (sessionId: string) => void | Promise<void>
  deleteSession: (sessionId: string) => void | Promise<void>
  renameSession: (sessionId: string, title: string) => void | Promise<void>
}

export function createEmptyChatBridge(): ChatBridge {
  return {
    ready: false,
    busy: false,
    activeSessionId: '',
    sessions: [],
    newChat: () => {},
    switchSession: () => {},
    deleteSession: () => {},
    renameSession: () => {},
  }
}

export const CHAT_BRIDGE_KEY: InjectionKey<Ref<ChatBridge>> = Symbol('chatBridge')
