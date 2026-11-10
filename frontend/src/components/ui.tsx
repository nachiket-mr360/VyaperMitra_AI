import { useEffect, useState, type ReactNode } from 'react'
import { usePrefersReducedMotion } from '../lib/format'

export function Surface({
  children,
  className = '',
  delay,
}: {
  children: ReactNode
  className?: string
  delay?: 1 | 2 | 3
}) {
  const enter = delay === 2 ? 'vm-enter-2' : delay === 3 ? 'vm-enter-3' : 'vm-enter'
  return <div className={`vm-glass min-w-0 rounded-2xl p-4 sm:rounded-3xl sm:p-6 ${enter} ${className}`}>{children}</div>
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-dashed border-stone-300 bg-white/50 px-3 py-3 text-left sm:px-4 sm:py-3">
      <p className="font-display text-base text-stone-800">{title}</p>
      <p className="mt-1 text-sm leading-snug text-stone-600">{body}</p>
    </div>
  )
}

export function Kpi({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint: string
}) {
  return (
    <Surface className="min-h-0 p-3 sm:p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-800/80">{label}</p>
      <p className="mt-1 break-words font-display text-2xl font-semibold tracking-tight sm:text-4xl">{value}</p>
      <p className="mt-1 truncate text-xs text-stone-500 sm:text-sm">{hint}</p>
    </Surface>
  )
}

export function CountInr({ amount }: { amount: number }) {
  const reduce = usePrefersReducedMotion()
  const [shown, setShown] = useState(reduce ? amount : 0)
  useEffect(() => {
    if (reduce) {
      setShown(amount)
      return
    }
    const start = performance.now()
    const from = 0
    const dur = 700
    let frame = 0
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur)
      const eased = 1 - (1 - p) ** 3
      setShown(from + (amount - from) * eased)
      if (p < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [amount, reduce])
  return <>₹{Math.round(shown).toLocaleString('en-IN')}</>
}

export function PageTitle({ kicker, title, sub }: { kicker: string; title: string; sub: string }) {
  return (
    <header className="vm-enter mb-4 min-w-0 sm:mb-6">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-800">{kicker}</p>
      <h1 className="mt-1 break-words font-display text-2xl font-semibold tracking-tight text-stone-900 sm:text-4xl">{title}</h1>
      <p className="mt-2 hidden max-w-2xl text-sm leading-relaxed text-stone-600 sm:block sm:text-base">{sub}</p>
    </header>
  )
}
