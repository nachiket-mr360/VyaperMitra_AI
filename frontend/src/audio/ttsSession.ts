import { splitSpeakable } from './ttsSentences'

export type SpeakFn = (text: string, language: string, signal?: AbortSignal) => Promise<Blob>

export type PlayFn = (blob: Blob) => Promise<void>

export type TtsTimings = {
  tts_requests: number
  first_tts_request_ms: number | null
  first_tts_complete_ms: number | null
  first_play_start_ms: number | null
  playback_total_ms: number | null
  chunks: number
  skipped: number
  inter_sentence_gap_ms: number[]
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
    inter_sentence_gap_ms: [],
  }
  if (!chunks.length) return timings

  const ac = new AbortController()
  const stale = () => !opts.isCurrent(opts.turn) || ac.signal.aborted
  const abortTurn = () => {
    if (!ac.signal.aborted) ac.abort()
  }

  const fetchChunk = async (index: number): Promise<Blob | null> => {
    if (stale()) return null
    if (index === 0 && timings.first_tts_request_ms == null) {
      timings.first_tts_request_ms = Math.round(now() - t0)
    }
    timings.tts_requests += 1
    try {
      const blob = await opts.speak(chunks[index] ?? '', opts.language, ac.signal)
      if (index === 0 && timings.first_tts_complete_ms == null) {
        timings.first_tts_complete_ms = Math.round(now() - t0)
      }
      if (stale()) return null
      return blob
    } catch {
      timings.skipped += 1
      return null
    }
  }

  let current = await fetchChunk(0)
  for (let i = 0; i < chunks.length; i += 1) {
    if (stale()) {
      abortTurn()
      break
    }
    const nextP = i + 1 < chunks.length ? fetchChunk(i + 1) : null
    if (current) {
      if (timings.first_play_start_ms == null) {
        timings.first_play_start_ms = Math.round(now() - t0)
      }
      try {
        await opts.play(current)
      } catch {
        timings.skipped += 1
      }
    }
    const gapT0 = now()
    if (stale()) {
      abortTurn()
      break
    }
    current = nextP ? await nextP : null
    if (nextP) {
      timings.inter_sentence_gap_ms.push(Math.round(now() - gapT0))
    }
  }
  abortTurn()
  timings.playback_total_ms = Math.round(now() - t0)
  return timings
}
