export interface CurrentUser {
  id: string
  displayName: string
  username: string
  email: string
  role: string
  department: string
}

export const GUEST_USER: CurrentUser = {
  id: 'guest',
  displayName: '未登录',
  username: 'guest',
  email: '',
  role: '访客',
  department: '—',
}

const ROLE_LABEL: Record<string, string> = {
  ANALYST: '投研分析师',
  CHECKER: '合规复核员',
  RM: '客户经理',
  ADMIN: '系统管理员',
}

const DEPT_LABEL: Record<string, string> = {
  research: '投研',
  compliance: '合规',
  rm: '客户经理部',
}

export function roleLabel(role: string | undefined): string {
  if (!role) return '访客'
  return ROLE_LABEL[role] ?? role
}

export function deptLabel(dept: string | undefined): string {
  if (!dept) return '—'
  return DEPT_LABEL[dept] ?? dept
}

export function canSubmitTickets(role: string | undefined): boolean {
  return role === 'ANALYST' || role === 'CHECKER' || role === 'ADMIN'
}

export function canReviewTickets(role: string | undefined): boolean {
  return role === 'CHECKER' || role === 'ADMIN'
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
