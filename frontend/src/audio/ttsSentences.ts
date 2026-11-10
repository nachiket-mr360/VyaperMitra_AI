/** Split assistant replies into speakable TTS chunks. Keep in sync with backend/tts_sentences.py */

const ABBREV = new Set([
  'mr',
  'mrs',
  'ms',
  'dr',
  'sr',
  'jr',
  'vs',
  'etc',
  'rs',
  'no',
  'nos',
  'kg',
  'g',
  'ml',
  'l',
  'ltd',
  'inc',
  'st',
  'nd',
  'rd',
  'th',
])

const MIN_SHORT = 28

function isAbbrev(before: string): boolean {
  const m = before.match(/([A-Za-z\u0900-\u097F\u0C80-\u0CFF]+)\.$/)
  if (!m?.[1]) return false
  return ABBREV.has(m[1].toLowerCase())
}

function isDecimal(before: string, after: string): boolean {
  return /\d$/.test(before) && /^\d/.test(after)
}

function isInitial(before: string): boolean {
  return /(?:^|[\s(])[A-Z]$/.test(before)
}

export function splitSpeakable(text: string): string[] {
  const raw = text.replace(/\s+/g, ' ').trim()
  if (!raw) return []
  const enders = /[.!?।]/g
  const cuts: number[] = []
  let m: RegExpExecArray | null
  while ((m = enders.exec(raw))) {
    const idx = m.index
    const before = raw.slice(0, idx + 1)
    const after = raw.slice(idx + 1)
    if (isDecimal(raw.slice(0, idx), raw.slice(idx + 1))) continue
    if (raw[idx] === '.' && (isAbbrev(before) || isInitial(raw.slice(0, idx)))) continue
    if (!after.trim()) {
      cuts.push(idx + 1)
      continue
    }
    if (/^\s/.test(after) || /[।]/.test(raw[idx] ?? '')) cuts.push(idx + 1)
  }
  const internal = cuts.filter((c) => c < raw.length)
  if (!internal.length) {
    return [raw]
  }
  const parts: string[] = []
  let start = 0
  for (const c of cuts) {
    const piece = raw.slice(start, c).trim()
    if (piece) parts.push(piece)
    start = c
  }
  const tail = raw.slice(start).trim()
  if (tail) parts.push(tail)
  const merged: string[] = []
  for (const p of parts) {
    const last = merged[merged.length - 1]
    const lastComplete = Boolean(last && /[.!?।]$/.test(last))
    if (last && !lastComplete && last.length < MIN_SHORT) {
      merged[merged.length - 1] = `${last} ${p}`
    } else if (last && !lastComplete && p.length < 12) {
      merged[merged.length - 1] = `${last} ${p}`
    } else {
      merged.push(p)
    }
  }
  return merged.length ? merged : [raw]
}
