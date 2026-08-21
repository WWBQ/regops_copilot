const MODEL_LABELS: Record<string, string> = {
  deepseek: 'DeepSeek',
  qwen: '通义千问',
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
