const TTS_LANGS = new Set(['en', 'hi', 'kn', 'mr'])

/** Map STT/intent language tags to Gnani TTS codes. Unknown → en. */
export function ttsLanguage(...candidates: Array<string | null | undefined>): string {
  for (const raw of candidates) {
    if (!raw || typeof raw !== 'string') continue
    const base = raw.trim().toLowerCase().split(/[-_]/)[0]
    if (base && TTS_LANGS.has(base)) return base
  }
  return 'en'
}
