export interface PageMenuItem {
  id: string
  label: string
  path?: string
  action?: 'new-chat'
  icon?: 'plus' | 'list'
}

/** 左侧页面菜单：按路由匹配（最长前缀） */
export const PAGE_MENUS: Record<string, PageMenuItem[]> = {
  '/quality/review': [
    { id: 'review-pending', label: '待审核', path: '/quality/review/pending', icon: 'list' },
    { id: 'review-completed', label: '已审核', path: '/quality/review/completed', icon: 'list' },
  ],
  '/quality/data': [
    { id: 'quality-gates', label: '质量门', path: '/quality/gates', icon: 'list' },
    { id: 'quality-facts', label: '财务事实库', path: '/quality/facts', icon: 'list' },
    { id: 'quality-reports', label: 'PDF 年报', path: '/quality/reports', icon: 'list' },
  ],
  '/ops/monitor': [
    { id: 'rag-monitor', label: 'RAG 检索监控', path: '/ops/monitor/rag', icon: 'list' },
    { id: 'asknum-monitor', label: '问数监控', path: '/ops/monitor/asknum', icon: 'list' },
    { id: 'agent-monitor', label: 'Agent 监控', path: '/ops/monitor/agent', icon: 'list' },
  ],
}

export function pageMenuForPath(path: string): PageMenuItem[] {
  if (path === '/' || path.startsWith('/rag') || path.startsWith('/risk-agent')) {
    return [{ id: 'new-chat', label: '新对话', action: 'new-chat', icon: 'plus' }]
  }
  if (path.startsWith('/quality/review')) {
    return PAGE_MENUS['/quality/review'] ?? []
  }
  if (path.startsWith('/quality/gates') || path.startsWith('/quality/facts') || path.startsWith('/quality/reports')) {
    return PAGE_MENUS['/quality/data'] ?? []
  }
  if (path.startsWith('/ops/monitor')) {
    return PAGE_MENUS['/ops/monitor'] ?? []
  }
  return []
}
