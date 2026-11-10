import type { ReactNode } from 'react'

export type NavId = 'dashboard' | 'inventory' | 'sales' | 'planner' | 'insights' | 'settings'

const NAV: { id: NavId; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'sales', label: 'Sales' },
  { id: 'planner', label: 'Planner' },
  { id: 'insights', label: 'Insights' },
  { id: 'settings', label: 'Settings' },
]

const MOBILE_NAV = NAV.filter((n) => n.id !== 'settings')

function VoiceButton({ onVoice, className }: { onVoice: () => void; className: string }) {
  return (
    <button
      type="button"
      data-testid="voice-fab"
      aria-label="Open voice assistant"
      onClick={onVoice}
      className={`flex items-center justify-center rounded-full bg-gradient-to-br from-teal-400 to-teal-800 text-xl text-white shadow-lg shadow-teal-900/30 hover:scale-105 ${className}`}
    >
      <span aria-hidden>🎙️</span>
    </button>
  )
}

export function AppShell({
  page,
  onPage,
  onVoice,
  children,
}: {
  page: NavId
  onPage: (id: NavId) => void
  onVoice: () => void
  children: ReactNode
}) {
  return (
    <div className="flex h-svh max-h-svh w-full min-w-0 overflow-hidden">
      <aside className="hidden h-full w-56 shrink-0 flex-col overflow-y-auto bg-[var(--vm-sidebar)] px-3 py-6 text-white lg:flex lg:w-60">
        <p className="px-2 text-xs font-semibold uppercase tracking-[0.2em] text-teal-200/80">Your Business</p>
        <p className="mt-1 px-2 font-display text-2xl">VyaparMitra</p>
        <nav className="mt-8 grid gap-1">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              data-testid={`nav-${item.id}`}
              onClick={() => onPage(item.id)}
              className={`min-h-12 rounded-2xl px-3 text-left text-base transition ${
                page === item.id ? 'bg-white/15 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <p className="mt-auto px-2 pt-6 text-xs leading-relaxed text-white/40">
          Talk with the button at the bottom centre. Records stay on your shop server.
        </p>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-stone-200/70 bg-white/70 px-4 py-3 backdrop-blur lg:hidden">
          <p className="font-display text-lg">VyaparMitra</p>
          <button
            type="button"
            data-testid="mnav-settings"
            className="min-h-11 rounded-full border border-stone-300 bg-white px-4 text-sm"
            onClick={() => onPage('settings')}
          >
            Settings
          </button>
        </header>

        <div className="vm-main-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 pt-4 sm:px-6 lg:px-10">
          {children}
          <div className="h-6 shrink-0 lg:hidden" aria-hidden="true" />
        </div>

        <nav className="relative z-30 border-t border-stone-200 bg-white/95 px-1 pb-[max(0.4rem,env(safe-area-inset-bottom))] pt-[3.35rem] backdrop-blur lg:hidden">
          <VoiceButton
            onVoice={onVoice}
            className="absolute left-1/2 top-2 z-10 h-14 w-14 -translate-x-1/2"
          />
          <div className="grid grid-cols-5 gap-0.5">
            {MOBILE_NAV.map((item) => (
              <button
                key={item.id}
                type="button"
                data-testid={`mnav-${item.id}`}
                onClick={() => onPage(item.id)}
                className={`min-h-12 min-w-0 overflow-hidden rounded-xl px-0.5 text-[10px] font-medium leading-tight sm:text-xs ${
                  page === item.id ? 'bg-teal-800 text-white' : 'text-stone-600'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </nav>

        <div className="relative hidden h-20 shrink-0 items-center justify-center border-t border-stone-200/80 bg-white/80 lg:flex">
          <VoiceButton onVoice={onVoice} className="h-16 w-16" />
        </div>
      </div>
    </div>
  )
}
