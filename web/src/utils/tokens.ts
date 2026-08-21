/** 前端估算用户输入 Token（中文约 1 字 1 token，英文约 4 字符 1 token） */
export function estimateTokens(text: string): number {
  const trimmed = text.trim()
  if (!trimmed) {
    return 0
  }
  let count = 0
  for (const char of trimmed) {
    if (/[\u4e00-\u9fff]/.test(char)) {
      count += 1
    } else if (!/\s/.test(char)) {
      count += 0.25
    }
  }
  return Math.max(1, Math.ceil(count))
}

export function formatLatency(ms: number): string {
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(1)}s`
  }
  return `${Math.round(ms)}ms`
}

export function formatTokenCount(count: number): string {
  return count.toLocaleString('zh-CN')
}

/** 从接口响应解析模型输出 Token（completion），避免误用 total */
export function resolveCompletionTokens(response: {
  completion_tokens?: number
  total_tokens?: number
  prompt_tokens?: number
}): number {
  if (response.completion_tokens != null) {
    return response.completion_tokens
  }
  if (response.total_tokens != null && response.prompt_tokens != null) {
    return Math.max(0, response.total_tokens - response.prompt_tokens)
  }
  return 0
}
