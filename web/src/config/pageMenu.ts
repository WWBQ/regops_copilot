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
}

export function pageMenuForPath(path: string): PageMenuItem[] {
  if (path === '/' || path.startsWith('/rag')) {
    return [{ id: 'new-chat', label: '新对话', action: 'new-chat', icon: 'plus' }]
  }
  if (path.startsWith('/quality/review')) {
    return PAGE_MENUS['/quality/review'] ?? []
  }
  return []
}
