import assert from 'node:assert/strict'
import test from 'node:test'

import { pageMenuForPath } from '../src/config/pageMenu.ts'
import { NAV_GROUPS } from '../src/config/nav.ts'

test('removed audit page has no navigation entry', () => {
  assert.deepEqual(pageMenuForPath('/compliance/audit'), [])
  assert.deepEqual(pageMenuForPath('/compliance/audit/risks'), [])
  assert.equal(NAV_GROUPS.some((group) => group.items.some((item) => item.id === 'audit')), false)
})
