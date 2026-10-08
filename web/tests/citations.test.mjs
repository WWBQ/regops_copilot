import assert from 'node:assert/strict'
import test from 'node:test'

import { createServer } from 'vite'

const vite = await createServer({
  configFile: false,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
})
const { attachCitationMarks, injectInlineCitationMarkers } = await vite.ssrLoadModule('/src/utils/citations.ts')

test.after(async () => {
  await vite.close()
})

test('risk Agent keeps sparse citation_id in body and links to the matching evidence', () => {
  const citations = [
    { citation_id: 7, doc_id: 'report-a', page: 1, snippet: 'A' },
    { citation_id: 9, doc_id: 'report-b', page: 2, snippet: 'B' },
    { citation_id: 34, doc_id: 'report-c', page: 3, snippet: 'C' },
  ]
  const bound = attachCitationMarks('依据 [34] 和 [7]；未知 [18]。', citations)
  assert.equal(bound.content, '依据 [34] 和 [7]；未知 [18]。')
  assert.deepEqual(bound.citations, citations)
  const html = injectInlineCitationMarkers(bound.content, bound.citations)
  assert.match(html, /data-cite-index="2"[^>]*>34<\/button>/u)
  assert.match(html, /data-cite-index="0"[^>]*>7<\/button>/u)
  assert.match(html, /未知 \[18\]/u)
})

test('compliance citations still use positional numbering', () => {
  const citations = [
    { doc_id: 'report-a', page: 1, snippet: 'A' },
    { doc_id: 'report-b', page: 2, snippet: 'B' },
  ]
  const bound = attachCitationMarks('依据 [2]。', citations)
  assert.equal(bound.content, '依据 [1]。')
  assert.deepEqual(bound.citations, [citations[1]])
  const html = injectInlineCitationMarkers(bound.content, bound.citations)
  assert.match(html, /data-cite-index="0"[^>]*>1<\/button>/u)
})
