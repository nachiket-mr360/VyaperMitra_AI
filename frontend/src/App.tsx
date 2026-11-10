import { useEffect, useState } from 'react'
import { HomeDashboard } from './components/dashboard/HomeDashboard'
import { InsightsPage } from './components/insights/InsightsPage'
import { InventoryPage } from './components/inventory/InventoryPage'
import { AppShell, type NavId } from './components/layout/AppShell'
import { Planner } from './components/Planner'
import { SalesPage } from './components/sales/SalesPage'
import { SettingsPage } from './components/settings/SettingsPage'
import { VoiceOverlay } from './components/voice/VoiceOverlay'
import { readLanguageMode, writeLanguageMode, type LanguageMode } from './lib/languagePreference'

function readDebug() {
  if (typeof window === 'undefined') return false
  if (new URLSearchParams(window.location.search).get('debug') === '1') return true
  return window.localStorage.getItem('vyaparmitra.debug') === '1'
}

export default function App() {
  const [page, setPage] = useState<NavId>('dashboard')
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [debug, setDebug] = useState(readDebug)
  const [languageMode, setLanguageMode] = useState<LanguageMode>(readLanguageMode)
  const [range, setRange] = useState<{ from?: string; to?: string }>({})

  useEffect(() => {
    window.localStorage.setItem('vyaparmitra.debug', debug ? '1' : '0')
  }, [debug])

  return (
    <>
      <AppShell page={page} onPage={setPage} onVoice={() => setVoiceOpen(true)}>
        {page === 'dashboard' && <HomeDashboard initialFrom={range.from} initialTo={range.to} />}
        {page === 'inventory' && <InventoryPage />}
        {page === 'sales' && <SalesPage />}
        {page === 'planner' && (
          <div className="min-w-0 pb-8">
            <Planner />
          </div>
        )}
        {page === 'insights' && <InsightsPage />}
        {page === 'settings' && (
          <SettingsPage
            debug={debug}
            onDebug={setDebug}
            languageMode={languageMode}
            onLanguageMode={(m) => {
              setLanguageMode(m)
              writeLanguageMode(m)
            }}
          />
        )}
      </AppShell>
      <VoiceOverlay
        open={voiceOpen}
        onClose={() => setVoiceOpen(false)}
        debug={debug}
        languageMode={languageMode}
        onLanguageMode={(m) => {
          setLanguageMode(m)
          writeLanguageMode(m)
        }}
        onOpenDashboard={(nav, from, to) => {
          const pageMap: Record<string, NavId> = {
            insights: 'insights',
            sales: 'sales',
            inventory: 'inventory',
            dashboard: 'dashboard',
          }
          setRange({ from: from || undefined, to: to || undefined })
          setPage(pageMap[nav] || 'insights')
          setVoiceOpen(false)
        }}
      />
    </>
  )
}
