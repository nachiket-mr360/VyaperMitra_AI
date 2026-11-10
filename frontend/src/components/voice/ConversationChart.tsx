import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CountInr } from '../ui'
import { usePrefersReducedMotion } from '../../lib/format'
import type { VisualizationPayload } from '../../lib/visualization'

function ChartBox({ children }: { children: (w: number, h: number) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 0, h: 176 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const apply = () => {
      const w = Math.floor(el.getBoundingClientRect().width)
      if (w > 0) setBox({ w, h: 176 })
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={ref} className="mt-2 h-44 w-full min-w-0">
      {box.w > 8 ? children(box.w, box.h) : null}
    </div>
  )
}

export function ConversationChart({
  viz,
  onOpenDashboard,
  compact,
}: {
  viz: VisualizationPayload
  onOpenDashboard?: (page: string, from?: string | null, to?: string | null) => void
  compact?: boolean
}) {
  const data = viz.points.map((p) => ({ ...p }))
  const horizontal = viz.type === 'hbar'
  const page = viz.dashboard?.page || 'insights'
  const animate = !usePrefersReducedMotion()

  return (
    <div className="mt-3 w-full min-w-0 rounded-2xl border border-white/15 bg-black/30 p-3">
      <p className="text-sm font-medium text-white">{viz.title}</p>
      {viz.subtitle ? <p className="mt-1 text-xs text-white/60">{viz.subtitle}</p> : null}
      {viz.kpis && viz.kpis.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {viz.kpis.map((k) => (
            <div key={k.label} className="rounded-xl bg-white/5 px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-white/50">{k.label}</p>
              <p className="font-display text-lg text-teal-100">
                {viz.metric === 'recorded_sales_amount' && k.label.toLowerCase().includes('sales') ? (
                  <CountInr amount={k.value} />
                ) : (
                  k.value
                )}
              </p>
            </div>
          ))}
        </div>
      )}
      {data.length === 0 ? (
        <p className="mt-3 text-sm text-white/70">No chartable recorded figures for this question.</p>
      ) : (
        <ChartBox>
          {(w, h) =>
            viz.type === 'line' ? (
              <LineChart width={w} height={h} data={data} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="label" tick={{ fill: '#cbd5e1', fontSize: 10 }} />
                <YAxis tick={{ fill: '#cbd5e1', fontSize: 10 }} width={40} />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="#5eead4" dot={false} isAnimationActive={animate} />
              </LineChart>
            ) : viz.type === 'area' ? (
              <AreaChart width={w} height={h} data={data} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="label" tick={{ fill: '#cbd5e1', fontSize: 10 }} />
                <YAxis tick={{ fill: '#cbd5e1', fontSize: 10 }} width={40} />
                <Tooltip />
                <Area type="monotone" dataKey="value" stroke="#5eead4" fill="#2dd4bf55" isAnimationActive={animate} />
              </AreaChart>
            ) : (
              <BarChart
                width={w}
                height={h}
                data={data}
                layout={horizontal ? 'vertical' : 'horizontal'}
                margin={{ top: 8, right: 8, left: horizontal ? 8 : 4, bottom: 4 }}
              >
                <CartesianGrid stroke="rgba(255,255,255,0.08)" />
                {horizontal ? (
                  <>
                    <XAxis type="number" tick={{ fill: '#cbd5e1', fontSize: 10 }} />
                    <YAxis type="category" dataKey="label" width={Math.min(96, Math.floor(w * 0.32))} tick={{ fill: '#cbd5e1', fontSize: 10 }} />
                  </>
                ) : (
                  <>
                    <XAxis dataKey="label" tick={{ fill: '#cbd5e1', fontSize: 10 }} />
                    <YAxis tick={{ fill: '#cbd5e1', fontSize: 10 }} width={40} />
                  </>
                )}
                <Tooltip />
                <Bar dataKey="value" fill="#5eead4" radius={4} isAnimationActive={animate} />
              </BarChart>
            )
          }
        </ChartBox>
      )}
      {!compact && onOpenDashboard && (
        <button
          type="button"
          className="mt-2 min-h-10 text-left text-xs text-teal-200/80 underline"
          onClick={() => onOpenDashboard(page, viz.dashboard?.from, viz.dashboard?.to)}
        >
          Also open Insights page
        </button>
      )}
    </div>
  )
}
