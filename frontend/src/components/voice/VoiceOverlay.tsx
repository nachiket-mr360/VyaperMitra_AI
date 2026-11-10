import { useEffect, useMemo, useState } from 'react'
import { useVoiceSession, type VoiceSessionState } from '../../hooks/useVoiceSession'
import { LANGUAGE_OPTIONS, modeLabel, type LanguageMode } from '../../lib/languagePreference'
import { validateVisualization, vizFingerprint } from '../../lib/visualization'
import { ConversationChart } from './ConversationChart'

const COPY: Record<VoiceSessionState, { label: string; hint: string }> = {
  idle: { label: 'Ready', hint: 'Opening the microphone…' },
  connecting: { label: 'Connecting', hint: 'Waiting for microphone permission.' },
  listening: { label: 'Listening', hint: 'Speak naturally. I will wait until you pause.' },
  processing: { label: 'Thinking', hint: 'Transcribing and checking your shop records.' },
  speaking: { label: 'Speaking', hint: 'You can interrupt me by talking.' },
  interrupted: { label: 'Interrupted', hint: 'Stopping playback…' },
  reconnecting: { label: 'Reconnecting', hint: 'Trying the microphone again.' },
  error: { label: 'Something went wrong', hint: 'I will try listening again shortly.' },
}

export function VoiceOverlay({
  open,
  onClose,
  debug,
  onOpenDashboard,
  languageMode,
  onLanguageMode,
}: {
  open: boolean
  onClose: () => void
  debug: boolean
  onOpenDashboard?: (page: string, from?: string | null, to?: string | null) => void
  languageMode: LanguageMode
  onLanguageMode: (mode: LanguageMode) => void
}) {
  const session = useVoiceSession(open, languageMode)
  const [tab, setTab] = useState<'talk' | 'board'>('talk')
  const [waitS, setWaitS] = useState(0)
  const { state, error, level, lines, pending } = session
  useEffect(() => {
    if (state !== 'processing') {
      setWaitS(0)
      return
    }
    const t0 = Date.now()
    const id = window.setInterval(() => setWaitS((Date.now() - t0) / 1000), 250)
    return () => window.clearInterval(id)
  }, [state])
  const board = useMemo(() => {
    const seen = new Set<string>()
    const items = []
    for (const line of lines) {
      if (line.role !== 'assistant' || !line.visualization) continue
      const viz = validateVisualization(line.visualization)
      if (!viz) continue
      const fp = vizFingerprint(viz)
      if (seen.has(fp)) continue
      seen.add(fp)
      items.push(viz)
    }
    return items
  }, [lines])
  if (!open) return null
  const copy = COPY[state]
  const orbScale = state === 'listening' ? 1 + Math.min(0.18, level * 4) : 1

  return (
    <div
      className="fixed inset-0 z-[60] flex min-h-0 flex-col overflow-hidden bg-[#070b14] text-white"
      role="dialog"
      aria-modal="true"
      aria-label="Voice assistant"
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-20 top-10 h-72 w-72 rounded-full bg-teal-500/20 blur-3xl" />
        <div className="absolute right-0 top-40 h-80 w-80 rounded-full bg-amber-400/10 blur-3xl" />
      </div>
      <div className="relative flex items-center justify-between px-4 py-4 sm:px-8">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium tracking-wide text-white/70">VyaparMitra</p>
          <label className="flex items-center gap-2 text-xs text-white/70">
            Language
            <select
              className="rounded-full bg-white/15 px-2 py-1 text-white"
              value={languageMode}
              onChange={(e) => onLanguageMode(e.target.value as LanguageMode)}
              aria-label="Response language"
            >
              {LANGUAGE_OPTIONS.map((o) => (
                <option key={o.id} value={o.id} className="text-stone-900">
                  {o.label}
                </option>
              ))}
            </select>
            <span className="hidden text-white/50 sm:inline">{modeLabel(languageMode)}</span>
          </label>
          <button
            type="button"
            className={`rounded-full px-3 py-1 text-xs ${tab === 'talk' ? 'bg-white/20' : 'text-white/50'}`}
            onClick={() => setTab('talk')}
          >
            Talk
          </button>
          <button
            type="button"
            className={`rounded-full px-3 py-1 text-xs ${tab === 'board' ? 'bg-white/20' : 'text-white/50'}`}
            onClick={() => setTab('board')}
          >
            Board{board.length ? ` (${board.length})` : ''}
          </button>
        </div>
        <button
          type="button"
          className="min-h-12 min-w-12 rounded-full border border-white/20 px-4 text-base"
          onClick={() => {
            void session.close()
            onClose()
          }}
        >
          Close
        </button>
      </div>
      <div className="relative mx-auto min-h-0 w-full max-w-lg flex-1 overflow-y-auto px-4">
        {tab === 'board' ? (
          <div className="pb-4">
            <p className="text-sm text-white/70">Recorded figures from this conversation. Latest charts stay on top of older ones.</p>
            {board.length === 0 ? (
              <p className="mt-3 text-white/50">No business charts yet.</p>
            ) : (
              [...board].reverse().map((viz, i) => (
                <ConversationChart key={`${viz.title}-${i}`} viz={viz} onOpenDashboard={onOpenDashboard} compact />
              ))
            )}
            <button type="button" className="mt-4 min-h-11 rounded-full border border-white/20 px-4" onClick={() => setTab('talk')}>
              Back to conversation
            </button>
          </div>
        ) : (
          <>
            {lines.length === 0 && (
              <>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-xs uppercase tracking-wider text-white/50">You</p>
                  <p className="mt-1 text-white/80">Your words will appear here.</p>
                </div>
                <div className="mt-3 rounded-2xl border border-white/10 bg-teal-500/10 p-4">
                  <p className="text-xs uppercase tracking-wider text-teal-200/80">Assistant</p>
                  <p className="mt-1 text-white/80">Replies will appear here. Purchases and sales still need your confirmation.</p>
                </div>
              </>
            )}
            {lines.slice(-12).map((line, i) => (
              <div
                key={`${line.role}-${i}-${line.text.slice(0, 12)}`}
                className={
                  line.role === 'user'
                    ? 'mt-3 rounded-2xl border border-white/10 bg-white/5 p-4'
                    : 'mt-3 rounded-2xl border border-white/10 bg-teal-500/10 p-4'
                }
              >
                <p className="text-xs uppercase tracking-wider text-white/50">{line.role === 'user' ? 'You' : 'Assistant'}</p>
                <p className="mt-1 text-white/90">{line.text}</p>
                {line.role === 'assistant' && line.visualization
                  ? (() => {
                      const viz = validateVisualization(line.visualization)
                      return viz ? <ConversationChart viz={viz} onOpenDashboard={onOpenDashboard} /> : (
                        <p className="mt-2 text-sm text-white/60">No chart for this reply.</p>
                      )
                    })()
                  : null}
              </div>
            ))}
            {pending?.needs_confirmation && (
              <div className="mt-3 rounded-2xl border border-amber-300/40 bg-amber-500/10 p-4">
                <p className="text-xs uppercase tracking-wider text-amber-200">Confirm</p>
                <p className="mt-1 text-white/90">{pending.message || pending.reply_text}</p>
                <div className="mt-3 flex gap-2">
                  <button type="button" className="min-h-11 rounded-full bg-white px-4 text-stone-900" onClick={() => void session.onConfirm()}>
                    Yes
                  </button>
                  <button type="button" className="min-h-11 rounded-full border border-white/30 px-4" onClick={() => void session.onCancel()}>
                    No
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="relative flex shrink-0 flex-col items-center px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2">
        <div
          className={`relative grid h-20 w-20 place-items-center rounded-full bg-gradient-to-br from-teal-300/80 to-teal-800 shadow-[0_0_80px_rgba(45,212,191,0.35)] sm:h-28 sm:w-28 ${state === 'listening' || state === 'speaking' ? '' : 'vm-orb-idle'}`}
          style={{ transform: `scale(${orbScale})` }}
        >
          {(state === 'listening' || state === 'speaking') && <span className="vm-fab-ring absolute inset-0 rounded-full" />}
          <span className="text-4xl" aria-hidden>
            {state === 'processing' ? '…' : '🎙️'}
          </span>
        </div>
        <p className="mt-2 font-display text-lg sm:text-xl">{copy.label}</p>
        <p className="mt-1 max-w-md text-center text-sm leading-relaxed text-white/70">
          {error || (state === 'processing' && waitS > 0.4 ? `Still working… ${waitS.toFixed(1)}s` : copy.hint)}
        </p>
        {debug && (
          <p className="mt-2 text-xs text-white/40">
            {state} · mic {level.toFixed(3)}
          </p>
        )}
      </div>
    </div>
  )
}
