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
    { id: 'label-create', label: '创建标注任务', path: '/quality/review/create', icon: 'plus' },
    { id: 'label-hall', label: '任务列表', path: '/quality/review', icon: 'list' },
  ],
  '/quality/gates': [
    { id: 'quality-facts', label: '财务事实库', path: '/quality/facts', icon: 'list' },
  ],
  '/quality/facts': [
    { id: 'quality-gates', label: '质量门', path: '/quality/gates', icon: 'list' },
  ],
  '/ops/rag': [
    { id: 'asknum-monitor', label: '问数监控', path: '/ops/asknum', icon: 'list' },
  ],
  '/ops/asknum': [
    { id: 'rag-monitor', label: 'RAG 检索监控', path: '/ops/rag', icon: 'list' },
    { id: 'llm-trace', label: 'LLM Trace', path: '/ops/traces', icon: 'list' },
    { id: 'eval', label: '评估报告', path: '/ops/eval', icon: 'list' },
  ],
  '/ops/traces': [
    { id: 'asknum-monitor', label: '问数监控', path: '/ops/asknum', icon: 'list' },
    { id: 'eval', label: '评估报告', path: '/ops/eval', icon: 'list' },
  ],
  '/compliance/review': [
    { id: 'compliance-audit', label: '审计追踪', path: '/compliance/audit', icon: 'list' },
    { id: 'users', label: '用户与权限', path: '/settings/users', icon: 'list' },
  ],
  '/compliance/workflow': [
    { id: 'compliance-review', label: '合规复核', path: '/compliance/review', icon: 'list' },
    { id: 'compliance-audit', label: '审计追踪', path: '/compliance/audit', icon: 'list' },
  ],
  '/compliance/audit': [
    { id: 'compliance-review', label: '合规复核', path: '/compliance/review', icon: 'list' },
  ],
}

export function pageMenuForPath(path: string): PageMenuItem[] {
  if (path === '/' || path.startsWith('/rag') || path.startsWith('/agent')) {
    return [{ id: 'new-chat', label: '新对话', action: 'new-chat', icon: 'plus' }]
  }
  if (path.startsWith('/quality/review')) {
    return PAGE_MENUS['/quality/review'] ?? []
  }
  if (path.startsWith('/quality/gates')) {
    return PAGE_MENUS['/quality/gates'] ?? []
  }
  if (path.startsWith('/quality/facts')) {
    return PAGE_MENUS['/quality/facts'] ?? []
  }
  if (path.startsWith('/ops/rag')) {
    return PAGE_MENUS['/ops/rag'] ?? []
  }
  if (path.startsWith('/ops/asknum')) {
    return PAGE_MENUS['/ops/asknum'] ?? []
  }
  if (path.startsWith('/ops/traces')) {
    return PAGE_MENUS['/ops/traces'] ?? []
  }
  if (path.startsWith('/compliance/workflow')) {
    return PAGE_MENUS['/compliance/workflow'] ?? []
  }
  if (path.startsWith('/compliance/audit')) {
    return PAGE_MENUS['/compliance/audit'] ?? []
  }
  if (path.startsWith('/compliance/review')) {
    return PAGE_MENUS['/compliance/review'] ?? []
  }
  return []
}
