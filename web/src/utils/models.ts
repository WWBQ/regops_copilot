const MODEL_LABELS: Record<string, string> = {
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  'deepseek-flash': 'DeepSeek V4.1 Flash',
  'deepseek-v4-pro': 'DeepSeek V4 Pro',
  'qwen3.8-max': 'Qwen 3.8 Max',
  'qwen3.8-flash': 'Qwen 3.8 Flash',
  'qwen3.7-plus': 'Qwen 3.7 Plus',
}

export function modelLabel(model: string): string {
  return MODEL_LABELS[model.toLowerCase()] ?? model
}

export const CHAT_MODEL_STORAGE_KEY = 'regops_chat_model'

export function loadStoredModel(fallback: string): string {
  try {
    return localStorage.getItem(CHAT_MODEL_STORAGE_KEY) ?? fallback
  } catch {
    return fallback
  }
}

export function storeModel(model: string): void {
  try {
    localStorage.setItem(CHAT_MODEL_STORAGE_KEY, model)
  } catch {
    // ignore
  }
}
