import { apiGet } from './client'

export type HealthResponse = {
  ok: boolean
  app: string
  phase: number
  timezone: string
  server_time: string
  database: {
    connected: boolean
    demo?: boolean
  }
  gnani: {
    enabled: boolean
    configured: boolean
    integration: string
    note: string
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/api/health')
}
