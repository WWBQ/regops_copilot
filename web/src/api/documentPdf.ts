import { documentContentUrl } from './documents'
import { authHeaders, ensureRequestId } from './client'

/** PDF 不能直接放在 object/iframe 的 /api 地址里：浏览器不会附带 Bearer Token。 */
export async function fetchDocumentPdf(docId: string, signal?: AbortSignal): Promise<Blob> {
  const headers = authHeaders({ Accept: 'application/pdf' })
  ensureRequestId(headers)
  let response: Response
  try {
    response = await fetch(documentContentUrl(docId), { headers, signal })
  } catch (cause) {
    if (signal?.aborted) throw cause
    throw new Error('无法连接文档服务，请检查 Java BFF 和 Python 服务')
  }
  if (response.status === 401) {
    throw new Error('登录已失效，请重新登录后打开年报')
  }
  if (response.status === 403) {
    throw new Error('没有查看这份年报的权限')
  }
  if (response.status === 404) {
    throw new Error('年报源文件不存在或已移除')
  }
  if (!response.ok) {
    throw new Error(`文档加载失败（HTTP ${response.status}）`)
  }
  if (!response.headers.get('Content-Type')?.toLowerCase().includes('application/pdf')) {
    throw new Error('文档服务未返回 PDF，请检查服务状态')
  }
  const blob = await response.blob()
  if (!blob.size) {
    throw new Error('年报 PDF 为空')
  }
  return blob
}
