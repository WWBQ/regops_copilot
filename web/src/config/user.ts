export interface CurrentUser {
  id: string
  displayName: string
  username: string
  email: string
  role: string
  department: string
}

/** 演示用户；W9+ 接入 java-service RBAC 后替换 */
export const CURRENT_USER: CurrentUser = {
  id: 'demo-user',
  displayName: '合规专员',
  username: 'compliance.demo',
  email: 'demo@regops.local',
  role: '合规分析师',
  department: '风险管理部',
}

export function userInitials(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) {
    return '?'
  }
  if (/^[\u4e00-\u9fff]/.test(trimmed)) {
    return trimmed.slice(-2)
  }
  const parts = trimmed.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  }
  return trimmed.slice(0, 2).toUpperCase()
}
