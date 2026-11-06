import { apiPostForm } from './client'

export type TranscribeResponse = {
  ok: boolean
  success: boolean
  transcript: string
  detected_language: string | null
  model: string
  request_id: string | null
  processing_time: number
  language_sent?: string
}

export async function transcribeAudio(blob: Blob, language: string): Promise<TranscribeResponse> {
  const form = new FormData()
  form.append('audio', blob, 'recording.wav')
  form.append('language', language)
  return apiPostForm<TranscribeResponse>('/api/voice/transcribe', form)
}
