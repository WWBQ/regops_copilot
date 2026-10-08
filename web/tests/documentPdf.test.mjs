import assert from 'node:assert/strict'
import test from 'node:test'

import { createServer } from 'vite'

const vite = await createServer({
  configFile: false,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
})
const { fetchDocumentPdf } = await vite.ssrLoadModule('/src/api/documentPdf.ts')

test.after(async () => {
  await vite.close()
})

test('PDF request carries the login token instead of relying on unauthenticated object URL', async () => {
  const previousFetch = globalThis.fetch
  const previousStorage = globalThis.localStorage
  let requestedUrl = ''
  let authorization = ''
  globalThis.localStorage = { getItem: () => 'test-jwt' }
  globalThis.fetch = async (url, init) => {
    requestedUrl = url
    authorization = init.headers.get('Authorization')
    return new Response('%PDF-1.4', { headers: { 'Content-Type': 'application/pdf' } })
  }
  try {
    const blob = await fetchDocumentPdf('000333_2024')
    assert.equal(requestedUrl, '/api/documents/000333_2024/content')
    assert.equal(authorization, 'Bearer test-jwt')
    assert.equal(await blob.text(), '%PDF-1.4')
  } finally {
    globalThis.fetch = previousFetch
    if (previousStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = previousStorage
  }
})

test('expired login is reported before trying to render PDF', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => new Response('', { status: 401 })
  try {
    await assert.rejects(fetchDocumentPdf('000333_2024'), /登录已失效/u)
  } finally {
    globalThis.fetch = previousFetch
  }
})

test('a PDF outside the current department is reported as forbidden', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => new Response('', { status: 403 })
  try {
    await assert.rejects(fetchDocumentPdf('000333_2024'), /没有查看这份年报的权限/u)
  } finally {
    globalThis.fetch = previousFetch
  }
})

test('missing source PDF is distinguishable from an authentication failure', async () => {
  const previousFetch = globalThis.fetch
  globalThis.fetch = async () => new Response('', { status: 404 })
  try {
    await assert.rejects(fetchDocumentPdf('000333_2024'), /年报源文件不存在/u)
  } finally {
    globalThis.fetch = previousFetch
  }
})
