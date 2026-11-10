/** Client-side energy VAD. Gnani REST STT has no documented server VAD. */

export const SPEECH_RMS = 0.018
export const BARGE_RMS = 0.05
export const MIN_SPEECH_MS = 450
export const SILENCE_MS = 1000
export const MAX_UTTERANCE_MS = 25000
export const POST_TTS_COOLDOWN_MS = 450
export const MAX_BUFFER_SAMPLES = 48000 * 28
export const START_CONFIRM_MS = 180
export const PREROLL_MS = 220
export const MIN_NOISE = 0.004
export const MAX_NOISE = 0.08

export function rms(frame: Float32Array): number {
  if (frame.length === 0) return 0
  let sum = 0
  for (let i = 0; i < frame.length; i += 1) {
    const s = frame[i] ?? 0
    sum += s * s
  }
  return Math.sqrt(sum / frame.length)
}

export function downsampleTo16k(input: Float32Array, fromRate: number): Float32Array {
  if (fromRate === 16000) return input
  const ratio = fromRate / 16000
  const outLen = Math.max(1, Math.floor(input.length / ratio))
  const out = new Float32Array(outLen)
  for (let i = 0; i < outLen; i += 1) {
    const src = i * ratio
    const i0 = Math.floor(src)
    const i1 = Math.min(i0 + 1, input.length - 1)
    const t = src - i0
    out[i] = (input[i0] ?? 0) * (1 - t) + (input[i1] ?? 0) * t
  }
  return out
}

export function speechThreshold(noise: number): number {
  const n = Math.min(MAX_NOISE, Math.max(MIN_NOISE, noise))
  return Math.min(0.12, Math.max(0.012, n * 2.6 + 0.006))
}

export function bargeThreshold(noise: number): number {
  return Math.max(BARGE_RMS, speechThreshold(noise) * 2.4)
}

export type VadDecision = {
  energy: number
  noise: number
  inSpeech: boolean
  start: boolean
  end: boolean
  barge: boolean
  keepFrame: boolean
}

/** Adaptive energy gate: tracks a noise floor, confirms speech start, hangover on end. */
export class AdaptiveVad {
  noise = 0.012
  calibMs = 0
  startMs = 0
  speechMs = 0
  silenceMs = 0
  inSpeech = false
  uttered = false
  elapsedMs = 0

  resetUtterance() {
    this.startMs = 0
    this.speechMs = 0
    this.silenceMs = 0
    this.inSpeech = false
    this.uttered = false
    this.elapsedMs = 0
  }

  recalibrate() {
    this.noise = 0.012
    this.calibMs = 0
    this.resetUtterance()
  }

  process(energy: number, frameMs: number, opts?: { speaking?: boolean; cooldown?: boolean }): VadDecision {
    const speaking = Boolean(opts?.speaking)
    const cooldown = Boolean(opts?.cooldown)
    const thr = speechThreshold(this.noise)
    const bargeThr = bargeThreshold(this.noise)

    if (speaking && !cooldown && energy >= bargeThr) {
      this.resetUtterance()
      this.inSpeech = true
      this.uttered = true
      this.speechMs = frameMs
      this.startMs = frameMs
      return {
        energy,
        noise: this.noise,
        inSpeech: true,
        start: true,
        end: false,
        barge: true,
        keepFrame: true,
      }
    }

    if (speaking || cooldown) {
      return {
        energy,
        noise: this.noise,
        inSpeech: false,
        start: false,
        end: false,
        barge: false,
        keepFrame: false,
      }
    }

    this.elapsedMs += frameMs
    const above = energy >= thr
    const nearNoise = energy < this.noise * 1.35 + 0.002

    if (!this.inSpeech) {
      if (nearNoise || !above) {
        const a = this.calibMs < 400 ? 0.25 : 0.04
        this.noise = Math.min(MAX_NOISE, Math.max(MIN_NOISE, this.noise * (1 - a) + energy * a))
        this.calibMs += frameMs
        this.startMs = 0
        return {
          energy,
          noise: this.noise,
          inSpeech: false,
          start: false,
          end: false,
          barge: false,
          keepFrame: true,
        }
      }
      this.startMs += frameMs
      if (this.startMs < START_CONFIRM_MS) {
        return {
          energy,
          noise: this.noise,
          inSpeech: false,
          start: false,
          end: false,
          barge: false,
          keepFrame: true,
        }
      }
      this.inSpeech = true
      this.uttered = true
      this.speechMs = this.startMs
      this.silenceMs = 0
      return {
        energy,
        noise: this.noise,
        inSpeech: true,
        start: true,
        end: false,
        barge: false,
        keepFrame: true,
      }
    }

    if (above) {
      this.speechMs += frameMs
      this.silenceMs = 0
    } else {
      this.silenceMs += frameMs
    }

    const end =
      this.uttered &&
      this.speechMs >= MIN_SPEECH_MS &&
      (this.silenceMs >= SILENCE_MS || this.elapsedMs >= MAX_UTTERANCE_MS)

    if (end) {
      const decision: VadDecision = {
        energy,
        noise: this.noise,
        inSpeech: false,
        start: false,
        end: true,
        barge: false,
        keepFrame: true,
      }
      this.resetUtterance()
      return decision
    }

    if (this.silenceMs > SILENCE_MS * 1.6 && this.speechMs < MIN_SPEECH_MS) {
      this.resetUtterance()
      return {
        energy,
        noise: this.noise,
        inSpeech: false,
        start: false,
        end: false,
        barge: false,
        keepFrame: false,
      }
    }

    return {
      energy,
      noise: this.noise,
      inSpeech: true,
      start: false,
      end: false,
      barge: false,
      keepFrame: true,
    }
  }
}

export const MIC_AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  channelCount: 1,
}

export async function openMicrophone(): Promise<{ stream: MediaStream; settings: MediaTrackSettings }> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('no_media')
  }
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: MIC_AUDIO_CONSTRAINTS })
  } catch {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  }
  const track = stream.getAudioTracks()[0]
  const settings = track?.getSettings?.() ?? {}
  return { stream, settings }
}
