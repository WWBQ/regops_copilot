import assert from 'node:assert/strict'
import test from 'node:test'

import { NAV_GROUPS } from '../src/config/nav.ts'
import { pageMenuForPath } from '../src/config/pageMenu.ts'

test('RAG, AskNum and Agent share one monitor navigation entry and sidebar', () => {
  const ops = NAV_GROUPS.find((group) => group.id === 'ops')
  assert.ok(ops)
  const monitors = ops.items.filter((item) => item.id === 'runtime-monitor')
  assert.equal(monitors.length, 1)
  assert.equal(monitors[0].path, '/ops/monitor/rag')
  assert.equal(ops.items.some((item) => item.label === 'LLM Trace'), false)
  assert.equal(ops.items.some((item) => item.id === 'logs'), false)

  const expected = [
    { id: 'rag-monitor', label: 'RAG 检索监控', path: '/ops/monitor/rag', icon: 'list' },
    { id: 'asknum-monitor', label: '问数监控', path: '/ops/monitor/asknum', icon: 'list' },
    { id: 'agent-monitor', label: 'Agent 监控', path: '/ops/monitor/agent', icon: 'list' },
  ]
  assert.deepEqual(pageMenuForPath('/ops/monitor/rag'), expected)
  assert.deepEqual(pageMenuForPath('/ops/monitor/asknum'), expected)
  assert.deepEqual(pageMenuForPath('/ops/monitor/agent'), expected)
})
