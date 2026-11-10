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

export async function speakText(text: string, language: string): Promise<Blob> {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language }),
  })
  if (!res.ok) {
    throw new Error('Speech playback failed')
  }
  return res.blob()
}

export async function transcribeAudio(blob: Blob, language: string): Promise<TranscribeResponse> {
  const form = new FormData()
  form.append('audio', blob, 'recording.wav')
  form.append('language', language)
  return apiPostForm<TranscribeResponse>('/api/voice/transcribe', form)
}
