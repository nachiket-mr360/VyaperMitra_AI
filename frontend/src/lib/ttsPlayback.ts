/** Browser-only rate. Gnani Timbre has no documented speed/pitch fields. */
export const TTS_PLAYBACK_RATE = 1.12

export function applyTtsPlayback(el: HTMLAudioElement, rate: number = TTS_PLAYBACK_RATE): void {
  const n = Number.isFinite(rate) ? Math.min(1.25, Math.max(1, rate)) : TTS_PLAYBACK_RATE
  el.preservesPitch = true
  el.playbackRate = n
}
