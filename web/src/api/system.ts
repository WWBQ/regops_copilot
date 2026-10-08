import { apiFetch } from './client'

export interface ServiceHealth {
  status: string
  service?: string
  latency_ms?: number | null
  installed?: boolean
  used_memory_bytes?: number | null
  connected_clients?: number | null
  queue_status?: string
  ready_messages?: number | null
  consumer_count?: number | null
}

export interface TrafficMinute {
  at: string
  count: number
  error_count: number
}

export interface SystemOverview {
  checked_at: string
  uptime_seconds: number
  services: {
    java_bff: ServiceHealth
    python_ai: ServiceHealth
    postgresql: ServiceHealth
    pgvector: ServiceHealth
    redis: ServiceHealth
    rabbitmq: ServiceHealth
  }
  requests: {
    total_since_start: number
    last_5m: number
    errors_5m: number
    error_rate_5m: number
    avg_latency_ms_5m: number | null
    in_flight: number
    per_minute: TrafficMinute[]
  }
  pressure: {
    cpu_percent: number | null
    heap_used_bytes: number
    heap_max_bytes: number | null
    heap_usage_percent: number | null
    thread_count: number
    available_processors: number
    load_average_1m: number | null
  }
}

export function getSystemOverview(): Promise<SystemOverview> {
  return apiFetch<SystemOverview>('/ops/system/overview')
}
