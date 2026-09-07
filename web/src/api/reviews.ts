import { apiFetch } from './client'

export type TicketStatus = 'PENDING' | 'SUBMITTED' | 'REVIEWED' | 'REJECTED'

export interface ReviewTicket {
  id: string
  status: TicketStatus
  dept: string
  companyCode: string
  companyCodes: string[]
  title: string
  reason: string
  conclusion: string
  riskLevel?: string | null
  clauseRefs?: string[] | null
  impactScope?: string | null
  threadId?: string | null
  submittedBy?: string | null
  reviewedBy?: string | null
  reviewReason?: string | null
  inputSummary?: string | null
  replayed: boolean
  createdAt: string
  updatedAt: string
}

export interface CreateTicketBody {
  company_code: string
  title: string
  reason: string
  conclusion?: string
  company_codes?: string[]
}

export function listTickets(status?: TicketStatus): Promise<ReviewTicket[]> {
  const query = status ? `?status=${status}` : ''
  return apiFetch(`/reviews/tickets${query}`)
}

export function getTicket(id: string): Promise<ReviewTicket> {
  return apiFetch(`/reviews/tickets/${id}`)
}

export function createTicket(body: CreateTicketBody, idempotencyKey?: string): Promise<ReviewTicket> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (idempotencyKey) {
    headers['Idempotency-Key'] = idempotencyKey
  }
  return apiFetch('/reviews/tickets', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
}

export function submitTicket(id: string): Promise<ReviewTicket> {
  return apiFetch(`/reviews/tickets/${id}/submit`, { method: 'POST' })
}

export function approveTicket(id: string, reason: string): Promise<ReviewTicket> {
  return apiFetch(`/reviews/tickets/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}

export function rejectTicket(id: string, reason: string): Promise<ReviewTicket> {
  return apiFetch(`/reviews/tickets/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
}
