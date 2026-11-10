export type LanguageMode = 'auto' | 'en' | 'hi' | 'kn' | 'mr'

export const LANGUAGE_OPTIONS: Array<{ id: LanguageMode; label: string }> = [
  { id: 'auto', label: 'Auto detect' },
  { id: 'en', label: 'English' },
  { id: 'hi', label: 'Hindi' },
  { id: 'kn', label: 'Kannada' },
  { id: 'mr', label: 'Marathi' },
]

const KEY = 'vyaparmitra.language_mode'

export function readLanguageMode(): LanguageMode {
  if (typeof window === 'undefined') return 'auto'
  const v = window.localStorage.getItem(KEY)
  if (v === 'en' || v === 'hi' || v === 'kn' || v === 'mr' || v === 'auto') return v
  return 'auto'
}

export function writeLanguageMode(mode: LanguageMode) {
  window.localStorage.setItem(KEY, mode)
}

export function sttLanguageForMode(mode: LanguageMode): string {
  if (mode === 'en') return 'en-IN'
  if (mode === 'hi') return 'hi-IN'
  if (mode === 'kn') return 'kn-IN'
  if (mode === 'mr') return 'mr-IN'
  return 'auto'
}

export function modeLabel(mode: LanguageMode): string {
  return LANGUAGE_OPTIONS.find((o) => o.id === mode)?.label || 'Auto detect'
}
