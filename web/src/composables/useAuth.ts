import { computed, ref } from 'vue'

import { fetchMe, login as loginApi, type AuthUser } from '../api/auth'
import { setAuthToken } from '../api/client'

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

  function logout() {
    persist(null, null)
  }

  async function refreshMe(): Promise<AuthUser | null> {
    try {
      const me = await fetchMe()
      persist(me)
      return me
    } catch {
      persist(null, null)
      return null
    }
  }

  return { user, loggedIn, login, logout, refreshMe }
}
