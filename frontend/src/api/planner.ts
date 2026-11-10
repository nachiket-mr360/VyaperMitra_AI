import { apiDelete, apiGet, apiPatchJson, apiPostJson } from './client'

export type Reminder = {
  id: number
  title: string
  due_date: string
  due_time: string | null
  due_at: string
  recurrence: string
  weekday?: number | null
  month_day?: number | null
  status: string
  overdue: boolean
  language: string
}

export type ShopNote = {
  id: number
  body: string
  created_at: string
  updated_at: string
}

export type Briefing = {
  ok: boolean
  timezone: string
  date: string
  today: Reminder[]
  overdue: Reminder[]
  upcoming: Reminder[]
  upcoming_total?: number
  upcoming_limit?: number
  notes: ShopNote[]
  notify_note: string
}

export function fetchBriefing() {
  return apiGet<Briefing>('/api/reminders/briefing')
}

export function fetchReminders(status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiGet<{ ok: boolean; reminders: Reminder[] }>(`/api/reminders${q}`)
}

export function createReminder(body: {
  title: string
  due_date: string
  due_time?: string | null
  recurrence?: string
}) {
  return apiPostJson<{ ok: boolean; reminder: Reminder }>('/api/reminders', body)
}

export async function completeReminder(id: number) {
  return apiPostJson<{ ok: boolean; reminder: Reminder }>(`/api/reminders/${id}/complete`, {})
}

export function deleteReminder(id: number) {
  return apiDelete<{ ok: boolean; reminder: Reminder }>(`/api/reminders/${id}`)
}

export function updateNote(id: number, body: string) {
  return apiPatchJson<{ ok: boolean; note: ShopNote }>(`/api/notes/${id}`, { body })
}

export function deleteNote(id: number) {
  return apiDelete<{ ok: boolean; note: ShopNote }>(`/api/notes/${id}`)
}

export function fetchNotes(q?: string) {
  const query = q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''
  return apiGet<{ ok: boolean; notes: ShopNote[] }>(`/api/notes${query}`)
}

export function createNote(body: string) {
  return apiPostJson<{ ok: boolean; note: ShopNote }>('/api/notes', { body })
}
