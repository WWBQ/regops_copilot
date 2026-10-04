import assert from 'node:assert/strict'
import test from 'node:test'

import {
  groupRiskAgentHistory,
  presentAgentRun,
  updateAgentTextPart,
} from '../src/views/agent/riskAgentPresentation.ts'

test('one question groups progress and conclusion into one assistant reply', () => {
  const citation = {
    doc_id: '002594_2024', page: 88, snippet: '营业收入增长', kind: 'document',
  }
  const riskResult = {
    id: 'result-1', company_code: '000333', company_name: '美的集团', year: 2024,
    status: 'partial', summary: '发现一条线索', evidence_gaps: ['缺少账龄'],
    findings: [{
      id: 'finding-1', risk_type: '盈利质量', severity: 'medium', conclusion: '需要核查',
      evidence_ids: [1], data_points: ['经营现金流'], uncertainty: '缺少明细',
      review_question: '是否存在非经常性影响？', review_status: 'pending_review',
    }],
  }
  const history = [
    { id: 'u1', author: 'user', chunks: [{ kind: 'text', text: '核查美的' }] },
    { id: 'a1', author: 'agent', chunks: [{ kind: 'text', text: '正在检索财务指标' }] },
    { id: 'a2', author: 'agent', chunks: [{ kind: 'text', text: '发现数据缺口' }] },
    {
      id: 'a3', author: 'agent', chunks: [{ kind: 'text', text: '结论：需人工核查 [1]' }],
      citations: [citation], risk_result: riskResult,
    },
    { id: 'u2', author: 'user', chunks: [{ kind: 'text', text: '下一家公司' }] },
    { id: 'a4', author: 'agent', chunks: [{ kind: 'text', text: '结论二' }] },
  ]
  const grouped = groupRiskAgentHistory(history)
  assert.deepEqual(grouped.map((item) => item.role), ['user', 'assistant', 'user', 'assistant'])
  assert.equal(grouped[1].content, '结论：需人工核查 [1]')
  assert.deepEqual(grouped[1].stages, ['正在检索财务指标', '发现数据缺口'])
  assert.deepEqual(grouped[1].citations, [citation])
  assert.deepEqual(grouped[1].riskResult, riskResult)
  assert.deepEqual(grouped[3].stages, [])
})

test('replace deltas update one stage rather than create repeated replies', () => {
  let parts = updateAgentTextPart([], 'stage-1', '检索', 'replace')
  parts = updateAgentTextPart(parts, 'stage-1', '检索完成', 'replace')
  parts = updateAgentTextPart(parts, 'stage-2', '结论', 'append')
  assert.deepEqual(presentAgentRun(parts), {
    content: '', stages: ['检索完成'], stageText: '结论',
  })
  assert.deepEqual(presentAgentRun(parts, '结论'), {
    content: '结论', stages: ['检索完成'], stageText: '',
  })
})

test('final answer split across blocks is not repeated in stages', () => {
  const parts = [
    { id: 'step', text: '检查事实库' },
    { id: 'answer-a', text: '证据不足，' },
    { id: 'answer-b', text: '需要人工复核。' },
  ]
  assert.deepEqual(presentAgentRun(parts, '证据不足，需要人工复核。'), {
    content: '证据不足，需要人工复核。', stages: ['检查事实库'], stageText: '',
  })
})
