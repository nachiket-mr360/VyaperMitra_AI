import { apiGet } from './client'

export type MemoryItem = {
  id: string
  layer: 'personal' | 'business'
  key: string
  value: string
  source: string
  updated_at: string
}

export function listMemories() {
  return apiGet<{ ok: boolean; memories: MemoryItem[] }>('/api/memory')
}
