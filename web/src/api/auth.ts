import { apiFetch } from './client'

export interface AuthUser {
  id: string
  username: string
  displayName: string
  email: string
  role: string
  dept: string
}

export interface LoginResponse {
  token: string
  tokenType: string
  expiresIn: number
  user: AuthUser
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function fetchMe(): Promise<AuthUser> {
  return apiFetch('/auth/me')
}

export function fetchDemoAccounts(): Promise<{ accounts: string[] }> {
  return apiFetch('/auth/demo-accounts')
}
