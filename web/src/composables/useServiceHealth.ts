import { ref, type InjectionKey, type Ref } from 'vue'

import { getHealth } from '../api/chat'

export type ServiceHealth = {
  javaOk: Ref<boolean | null>
  pythonOk: Ref<boolean | null>
  pythonError: Ref<string | null>
  modelName: Ref<string | null>
  refresh: () => Promise<void>
}

export const SERVICE_HEALTH_KEY: InjectionKey<ServiceHealth> = Symbol('serviceHealth')

export function createServiceHealth(): ServiceHealth {
  const javaOk = ref<boolean | null>(null)
  const pythonOk = ref<boolean | null>(null)
  const pythonError = ref<string | null>(null)
  const modelName = ref<string | null>(null)

  async function refresh() {
    try {
      const health = await getHealth()
      javaOk.value = health.status === 'ok'
      const py = health.pythonAi
      pythonOk.value = py?.status === 'ok'
      pythonError.value =
        py?.status === 'ok' ? null : String(py?.error_code ?? py?.error ?? 'down')
    } catch {
      javaOk.value = false
      pythonOk.value = false
      pythonError.value = 'bff_down'
    }
  }

  return { javaOk, pythonOk, pythonError, modelName, refresh }
}
