import { computed, ref } from 'vue'

import { fetchMe, login as loginApi, register as registerApi, type AuthUser } from '../api/auth'
import { ApiRequestError, setAuthToken } from '../api/client'

const USER_KEY = 'regops_user'

function readStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

const user = ref<AuthUser | null>(readStoredUser())

function persist(next: AuthUser | null, token?: string | null) {
  user.value = next
  try {
    if (next) {
      localStorage.setItem(USER_KEY, JSON.stringify(next))
    } else {
      localStorage.removeItem(USER_KEY)
    }
  } catch {
    /* ignore */
  }
  if (token !== undefined) {
    setAuthToken(token)
  }
}

export function useAuth() {
  const loggedIn = computed(() => Boolean(user.value))

  async function login(username: string, password: string): Promise<AuthUser> {
    const result = await loginApi(username, password)
    persist(result.user, result.token)
    return result.user
  }

  async function register(username: string, password: string, displayName: string, email: string): Promise<AuthUser> {
    const result = await registerApi(username, password, displayName, email)
    persist(result.user, result.token)
    return result.user
  }

  function logout() {
    persist(null, null)
  }

  async function refreshMe(): Promise<AuthUser | null> {
    try {
      const me = await fetchMe()
      persist(me)
      return me
    } catch (error) {
      if (error instanceof ApiRequestError && [401, 403].includes(error.status)) {
        persist(null, null)
        return null
      }
      throw error
    }
  }

  return { user, loggedIn, login, register, logout, refreshMe }
}
