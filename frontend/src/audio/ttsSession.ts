import { splitSpeakable } from './ttsSentences'

export type SpeakFn = (text: string, language: string) => Promise<Blob>

export type PlayFn = (blob: Blob) => Promise<void>

export type TtsTimings = {
  tts_requests: number
  first_tts_request_ms: number | null
  first_tts_complete_ms: number | null
  first_play_start_ms: number | null
  playback_total_ms: number | null
  chunks: number
  skipped: number
}

export async function playSpeakableChunks(opts: {
  text: string
  language: string
  turn: number
  isCurrent: (turn: number) => boolean
  speak: SpeakFn
  play: PlayFn
  now?: () => number
}): Promise<TtsTimings> {
  const now = opts.now ?? (() => performance.now())
  const t0 = now()
  const chunks = splitSpeakable(opts.text)
  const timings: TtsTimings = {
    tts_requests: 0,
    first_tts_request_ms: null,
    first_tts_complete_ms: null,
    first_play_start_ms: null,
    playback_total_ms: null,
    chunks: chunks.length,
    skipped: 0,
  }
  if (!chunks.length) return timings

  for (let i = 0; i < chunks.length; i += 1) {
    if (!opts.isCurrent(opts.turn)) break
    if (i === 0 && timings.first_tts_request_ms == null) {
      timings.first_tts_request_ms = Math.round(now() - t0)
    }
    timings.tts_requests += 1
    let blob: Blob | null = null
    try {
      blob = await opts.speak(chunks[i] ?? '', opts.language)
      if (i === 0 && timings.first_tts_complete_ms == null) {
        timings.first_tts_complete_ms = Math.round(now() - t0)
      }
    } catch {
      timings.skipped += 1
      continue
    }
    if (!opts.isCurrent(opts.turn)) break
    if (!blob) {
      timings.skipped += 1
      continue
    }
    if (timings.first_play_start_ms == null) {
      timings.first_play_start_ms = Math.round(now() - t0)
    }
    try {
      await opts.play(blob)
    } catch {
      timings.skipped += 1
    }
  }
  timings.playback_total_ms = Math.round(now() - t0)
  return timings
}
