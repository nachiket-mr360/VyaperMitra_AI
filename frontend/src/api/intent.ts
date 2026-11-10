import { apiPostJson } from './client'

export type IntentParseResponse = {
  ok: boolean
  transcript: string
  intent: string
  product_query: string | null
  quantity: number | null
  unit: string | null
  sale_amount: number | null
  missing: string[]
  candidates: Array<{ id: number; name: string; unit: string }>
  needs_confirmation: boolean
  pending_id: string | null
  create_product: boolean
  message: string
  error_code: string | null
  executed: boolean
  result: unknown
  reply_text?: string
  reply_language?: string
  product?: { name: string; unit: string; current_stock: number | null; stock_known?: boolean }
  suggested_aliases?: Array<{ alias: string; language: string }>
  canonical_name?: string
  visualization?: unknown
}

export function parseIntent(transcript: string, sessionId?: string, languageMode?: string) {
  return apiPostJson<IntentParseResponse>('/api/intents/parse', {
    transcript,
    ...(sessionId ? { session_id: sessionId } : {}),
    ...(languageMode ? { language_mode: languageMode } : {}),
  })
}

export function confirmIntent(pendingId: string, sessionId?: string) {
  return apiPostJson<{
    ok: boolean
    executed: boolean
    replayed?: boolean
    message: string
    result: unknown
    intent: string
  }>('/api/intents/confirm', {
    pending_id: pendingId,
    ...(sessionId ? { session_id: sessionId } : {}),
  })
}

export function cancelIntent(pendingId: string) {
  return apiPostJson<{ ok: boolean; cancelled: boolean; message: string }>(
    '/api/intents/cancel',
    { pending_id: pendingId },
  )
}
