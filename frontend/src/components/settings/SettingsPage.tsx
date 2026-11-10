import { useCallback, useEffect, useState } from 'react'
import { fetchHealth, type HealthResponse } from '../../api/health'
import { listMemories, type MemoryItem } from '../../api/memory'
import { VoicePanel } from '../VoicePanel'
import { LANGUAGE_OPTIONS, type LanguageMode } from '../../lib/languagePreference'
import { PageTitle, Surface } from '../ui'

export function SettingsPage({
  debug,
  onDebug,
  languageMode,
  onLanguageMode,
}: {
  debug: boolean
  onDebug: (v: boolean) => void
  languageMode: LanguageMode
  onLanguageMode: (mode: LanguageMode) => void
}) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [memories, setMemories] = useState<MemoryItem[]>([])

  const load = useCallback(async () => {
    setError(null)
    try {
      setHealth(await fetchHealth())
      try {
        const mem = await listMemories()
        setMemories(mem.memories || [])
      } catch {
        setMemories([])
      }
    } catch (err) {
      setHealth(null)
      setError(err instanceof Error ? err.message : 'Cannot reach the server.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="grid min-w-0 gap-6 pb-8">
      <PageTitle
        kicker="Settings"
        title="Shop preferences"
        sub="Connection and developer tools stay here so the main screens stay simple."
      />
      <Surface>
        <p className="text-sm text-stone-500">Server</p>
        {error && <p className="mt-2 text-red-800">{error}</p>}
        {health && (
          <p className="mt-2 text-lg">
            {health.ok ? 'Connected' : 'Not ready'}
            {health.database.name ? ` · ${health.database.name}` : ''}
          </p>
        )}
        <button type="button" className="mt-4 min-h-12 rounded-2xl bg-teal-800 px-4 text-white" onClick={() => void load()}>
          Check again
        </button>
      </Surface>
      <Surface>
        <p className="text-sm text-stone-500">Voice language</p>
        <p className="mt-2 text-sm text-stone-600">
          Auto detect uses each turn. A fixed language always answers in that language. Tamil is not supported.
        </p>
        <select
          className="mt-3 min-h-11 rounded-2xl border border-stone-300 bg-white px-3"
          value={languageMode}
          onChange={(e) => onLanguageMode(e.target.value as LanguageMode)}
          aria-label="Voice language"
        >
          {LANGUAGE_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </Surface>
      <Surface>
        <p className="text-sm text-stone-500">Memory</p>
        <p className="mt-2 text-sm text-stone-600">
          Personal and shop facts you asked me to remember. Sales and stock still come from shop records, not from this list.
        </p>
        {memories.length === 0 ? (
          <p className="mt-3 text-stone-500">Nothing stored yet. You can say “Remember that I prefer Marathi.”</p>
        ) : (
          <ul className="mt-3 grid gap-2 text-sm">
            {memories.map((m) => (
              <li key={m.id} className="rounded-xl bg-stone-50 px-3 py-2">
                <span className="text-stone-500">{m.layer} · {m.key}</span>
                <div>{m.value}</div>
              </li>
            ))}
          </ul>
        )}
      </Surface>
      <Surface>
        <label className="flex min-h-12 items-center gap-3 text-base">
          <input
            type="checkbox"
            checked={debug}
            onChange={(e) => onDebug(e.target.checked)}
          />
          Developer mode
        </label>
        <p className="mt-2 text-sm text-stone-500">
          Shows request details and the older voice test panel. Off for everyday shop use.
        </p>
      </Surface>
      {debug && health && (
        <Surface>
          <p className="text-sm text-stone-500">Diagnostics</p>
          <dl className="mt-3 grid gap-2 text-sm">
            <div>
              <dt className="text-stone-500">App</dt>
              <dd>
                {health.app} · phase {health.phase}
              </dd>
            </div>
            <div>
              <dt className="text-stone-500">Timezone</dt>
              <dd>{health.timezone}</dd>
            </div>
            <div>
              <dt className="text-stone-500">Gnani</dt>
              <dd>
                {health.gnani.integration} — {health.gnani.note}
              </dd>
            </div>
          </dl>
        </Surface>
      )}
      {debug && <VoicePanel />}
    </div>
  )
}
