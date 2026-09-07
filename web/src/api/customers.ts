import { apiFetch } from './client'

export interface CustomerProfile {
  id: string
  companyCode: string
  displayName: string
  classification: 'INTERNAL_RESEARCH' | 'CLIENT' | string
  maskedIdNo: string
  maskedPhone: string
  riskLevel: string
  notes: string
  dept: string
}

export function listCustomers(): Promise<CustomerProfile[]> {
  return apiFetch('/customers')
}

export function getCustomer(id: string): Promise<CustomerProfile> {
  return apiFetch(`/customers/${id}`)
}
