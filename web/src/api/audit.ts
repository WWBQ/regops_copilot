import { apiFetch } from './client'

export interface AuditEvent {
  id: number
  occurredAt: string
  actorUsername: string
  actorRole: string
  dept: string
  action: string
  entityType: string
  entityId: string
  requestId?: string | null
  reason: string
  inputSummary: string
  beforeJson: string
  afterJson: string
}

export function listAuditEvents(entityType?: string, entityId?: string): Promise<AuditEvent[]> {
  const params = new URLSearchParams()
  if (entityType) params.set('entityType', entityType)
  if (entityId) params.set('entityId', entityId)
  const query = params.toString()
  return apiFetch(`/audit/events${query ? `?${query}` : ''}`)
}
