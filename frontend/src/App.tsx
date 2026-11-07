import { useCallback, useEffect, useState } from 'react'
import { fetchHealth, type HealthResponse } from './api/health'
import { Dashboard } from './components/Dashboard'
import { VoicePanel } from './components/VoicePanel'

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'voice' | 'dashboard'>('dashboard')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchHealth()
      setHealth(data)
    } catch (err) {
      setHealth(null)
      setError(
        err instanceof Error
          ? err.message
          : 'Could not reach the VyaparMitra backend.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-6xl min-w-0 flex-col gap-6 overflow-x-hidden px-4 py-6 sm:px-6">
      <header>
        <p className="text-sm font-medium uppercase tracking-wide text-amber-800">
          Your Business, Your Voice
        </p>
        <h1 className="mt-1 text-3xl font-semibold">VyaparMitra</h1>
        <p className="mt-2 text-base text-stone-700 sm:text-lg">
          Your shop numbers, from your own records. Voice still needs confirm.
        </p>
      </header>

      <section className="rounded-2xl border border-stone-300 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-medium">Backend connection</h2>
        {loading && <p className="mt-3 text-lg">Checking server…</p>}
        {error && (
          <p className="mt-3 text-lg text-red-800" role="alert">
            {error}. Start the Flask server on port 5000.
          </p>
        )}
        {health && (
          <dl className="mt-4 grid gap-2 break-words text-base sm:text-lg">
            <div>
              <dt className="text-stone-500">Status</dt>
              <dd className="font-medium">{health.ok ? 'Connected' : 'Not ready'}</dd>
            </div>
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
              <dt className="text-stone-500">Server time</dt>
              <dd>{health.server_time}</dd>
            </div>
            <div>
              <dt className="text-stone-500">Database</dt>
              <dd>
                {health.database.connected ? 'SQLite connected' : 'Disconnected'}
                {health.database.demo ? ' · DEMO DATA' : ''}
              </dd>
            </div>
            <div>
              <dt className="text-stone-500">Gnani</dt>
              <dd>
                {health.gnani.integration} — {health.gnani.note}
              </dd>
            </div>
          </dl>
        )}
        <button
          type="button"
          onClick={() => void load()}
          className="mt-6 min-h-14 w-full rounded-xl bg-amber-700 px-4 text-lg font-medium text-white"
        >
          Check again
        </button>
      </section>

      <div className="flex flex-col gap-2 sm:grid sm:grid-cols-2">
        <button
          type="button"
          className={`min-h-14 min-w-0 overflow-hidden rounded-xl px-2 text-base sm:text-lg ${tab === 'dashboard' ? 'bg-amber-700 text-white' : 'border border-stone-400'}`}
          onClick={() => setTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          type="button"
          className={`min-h-14 min-w-0 overflow-hidden rounded-xl px-2 text-base sm:text-lg ${tab === 'voice' ? 'bg-amber-700 text-white' : 'border border-stone-400'}`}
          onClick={() => setTab('voice')}
        >
          Voice
        </button>
      </div>
      {tab === 'dashboard' ? <Dashboard /> : <VoicePanel />}
    </main>
  )
}

export default App
