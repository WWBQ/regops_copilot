import assert from 'node:assert/strict'
import test from 'node:test'

import { NAV_GROUPS } from '../src/config/nav.ts'
import { pageMenuForPath } from '../src/config/pageMenu.ts'

test('quality gates, facts and PDF reports share one top-level page and one sidebar', () => {
  const quality = NAV_GROUPS.find((group) => group.id === 'quality')
  assert.ok(quality)
  assert.deepEqual(quality.items.map((item) => item.id), ['quality-data', 'human-review'])
  const expected = [
    { id: 'quality-gates', label: '质量门', path: '/quality/gates', icon: 'list' },
    { id: 'quality-facts', label: '财务事实库', path: '/quality/facts', icon: 'list' },
    { id: 'quality-reports', label: 'PDF 年报', path: '/quality/reports', icon: 'list' },
  ]
  for (const path of ['/quality/gates', '/quality/facts', '/quality/reports']) {
    assert.deepEqual(pageMenuForPath(path), expected)
  }
  assert.deepEqual(pageMenuForPath('/quality/review/pending'), [
    { id: 'review-pending', label: '待审核', path: '/quality/review/pending', icon: 'list' },
    { id: 'review-completed', label: '已审核', path: '/quality/review/completed', icon: 'list' },
  ])
})
