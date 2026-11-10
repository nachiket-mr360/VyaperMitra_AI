import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Tooltip, XAxis, YAxis } from 'recharts'
import { ApiClientError } from '../../api/client'
import { fetchDashboard, type DashboardResponse } from '../../api/analytics'
import { fetchBriefing, type Briefing } from '../../api/planner'
import { addDaysISO, greetingForHour, inr, shortDate, usePrefersReducedMotion } from '../../lib/format'
import { exportUrl } from '../../lib/downloadCsv'
import { subscribeShopRecords } from '../../lib/shopRecords'
import { CountInr, EmptyState, Kpi, PageTitle, Surface } from '../ui'

type Preset = 'today' | 'yesterday' | '7d' | '30d'

function ChartBox({
  className,
  children,
}: {
  className: string
  children: (size: { w: number; h: number }) => ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      setSize({ w: Math.max(0, Math.floor(r.width)), h: Math.max(0, Math.floor(r.height)) })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={ref} className={className}>
      {size.w > 8 && size.h > 8 ? children(size) : null}
    </div>
  )
}

export function HomeDashboard({ initialFrom, initialTo }: { initialFrom?: string; initialTo?: string } = {}) {
  const [from, setFrom] = useState(initialFrom || '')
  const [to, setTo] = useState(initialTo || '')
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [brief, setBrief] = useState<Briefing | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const reduce = usePrefersReducedMotion()
  const loadGen = useRef(0)

  const load = useCallback(async (silent = false) => {
    const gen = ++loadGen.current
    if (!silent) setLoading(true)
    setError(null)
    try {
      const [dash, briefing] = await Promise.all([
        from && to ? fetchDashboard(from, to) : fetchDashboard(),
        fetchBriefing().catch(() => null),
      ])
      if (gen !== loadGen.current) return
      setData(dash)
      setBrief(briefing)
      if (!from || !to) {
        setFrom(dash.period.from)
        setTo(dash.period.to)
      }
    } catch (err) {
      if (gen !== loadGen.current) return
      setData(null)
      setError(err instanceof ApiClientError ? err.message : 'Could not load dashboard.')
    } finally {
      if (gen === loadGen.current && !silent) setLoading(false)
    }
  }, [from, to])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => subscribeShopRecords(() => void load(true)), [load])

  const hour = new Date().getHours()
  const periodHasSales = (data?.period.transactions ?? 0) > 0
  const knownStock = (data?.inventory ?? []).filter((p) => p.stock_known !== false && p.current_stock != null)
  const productCompare = (data?.by_product ?? []).filter((p) => p.amount > 0)
  const trendDaysWithSales = (data?.trend ?? []).filter((d) => d.transactions > 0).length
  const chartData = useMemo(
    () => (data?.trend ?? []).map((row) => ({ ...row, label: shortDate(row.date) })),
    [data],
  )

  function applyPreset(next: Preset) {
    if (!data) return
    const today = data.today.date
    const yest = data.yesterday.date
    if (next === 'today') {
      setFrom(today)
      setTo(today)
    } else if (next === 'yesterday') {
      setFrom(yest)
      setTo(yest)
    } else if (next === '7d') {
      setFrom(addDaysISO(today, -6))
      setTo(today)
    } else {
      setFrom(addDaysISO(today, -29))
      setTo(today)
    }
  }

  return (
    <div className="grid min-w-0 gap-4 pb-4 sm:gap-6">
      <PageTitle
        kicker="Home"
        title={`${greetingForHour(hour)}.`}
        sub="Recorded sales and counted stock — not cash in the till, and not profit."
      />
      {data && (
        <a
          className="inline-flex min-h-11 w-fit items-center rounded-2xl bg-teal-800 px-4 text-sm font-medium text-white"
          href={exportUrl('analytics', { from: data.period.from, to: data.period.to })}
          download
        >
          Download CSV
        </a>
      )}

      {loading && <p className="text-stone-600">Loading your shop numbers…</p>}
      {error && (
        <p className="text-red-800" role="alert">
          {error}
        </p>
      )}

      {data && (
        <>
          <div className="grid min-w-0 grid-cols-2 gap-3 xl:grid-cols-4">
            <Surface className="p-3 sm:p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-800/80">Today’s sales</p>
              <p className="mt-1 font-display text-2xl font-semibold sm:text-4xl">
                <CountInr amount={data.today.total_amount} />
              </p>
              <p className="mt-1 truncate text-xs text-stone-500 sm:text-sm">
                {data.today.transactions} bills · {data.today.date}
              </p>
            </Surface>
            <Kpi
              label="Yesterday"
              value={inr(data.yesterday.total_amount)}
              hint={`${data.yesterday.transactions} bills`}
            />
            <Kpi
              label="This period"
              value={inr(data.period.total_amount)}
              hint={`${data.period.from} → ${data.period.to}`}
            />
            <Kpi label="Bills" value={String(data.period.transactions)} hint="Recorded bills, not cash received" />
          </div>

          {(brief?.overdue.length || brief?.today.length) ? (
            <Surface delay={2} className="border-amber-200/80">
              <h2 className="font-display text-xl">Needs attention</h2>
              <ul className="mt-3 grid gap-2 text-base">
                {brief!.overdue.slice(0, 4).map((r) => (
                  <li key={`o-${r.id}`} className="text-red-800">
                    Overdue · {r.title}
                  </li>
                ))}
                {brief!.today.slice(0, 4).map((r) => (
                  <li key={`t-${r.id}`} className="text-stone-700">
                    Today · {r.title}
                  </li>
                ))}
              </ul>
            </Surface>
          ) : null}

          {data.low_stock.length > 0 && (
            <Surface delay={2}>
              <h2 className="font-display text-xl">Low stock</h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                {data.low_stock.map((p) => (
                  <li key={p.id} className="rounded-full bg-red-50 px-3 py-2 text-sm text-red-900">
                    {p.name}
                  </li>
                ))}
              </ul>
            </Surface>
          )}

          <Surface delay={2}>
            <div className="flex flex-nowrap gap-2 overflow-x-auto pb-1">
              {(['today', 'yesterday', '7d', '30d'] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  className="min-h-10 rounded-full border border-stone-200 bg-white px-3 text-sm hover:border-teal-700"
                  onClick={() => applyPreset(key)}
                >
                  {key === '7d' ? '7 days' : key === '30d' ? '30 days' : key === 'today' ? 'Today' : 'Yesterday'}
                </button>
              ))}
            </div>
            <div className="mt-3 hidden grid-cols-2 gap-3 sm:grid">
              <label className="min-w-0 text-sm text-stone-600">
                From
                <input
                  className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-2xl border border-stone-200 px-3"
                  type="date"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                />
              </label>
              <label className="min-w-0 text-sm text-stone-600">
                To
                <input
                  className="mt-1 min-h-12 w-full min-w-0 max-w-full rounded-2xl border border-stone-200 px-3"
                  type="date"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                />
              </label>
            </div>
          </Surface>

          <Surface delay={3}>
            <h2 className="font-display text-xl">Sales trend</h2>
            {periodHasSales && trendDaysWithSales > 0 ? (
              <p className="mt-1 text-sm text-stone-500">Daily recorded sales</p>
            ) : null}
            {!periodHasSales || trendDaysWithSales === 0 ? (
              <div className="mt-3">
                <EmptyState
                  title="No sales chart yet"
                  body="Record bills in this date range and a trend will appear. Empty days are not shown as a fake pattern."
                />
              </div>
            ) : (
              <ChartBox className="mt-3 h-48 w-full min-w-0 sm:h-56 lg:h-64">
                {({ w, h }) => (
                  <BarChart width={w} height={h} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="#e7e5e4" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} width={36} />
                    <Tooltip formatter={(v) => inr(Number(v))} />
                    <Bar dataKey="total_amount" fill="#0f766e" radius={[6, 6, 0, 0]} isAnimationActive={!reduce} />
                  </BarChart>
                )}
              </ChartBox>
            )}
          </Surface>

          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <Surface>
              <h2 className="font-display text-xl">Product performance</h2>
              {productCompare.length < 2 ? (
                <div className="mt-3">
                  <EmptyState
                    title="Not enough product sales"
                    body="Comparisons appear when at least two products have recorded sales in this period."
                  />
                </div>
              ) : (
                <ChartBox className="mt-3 h-48 w-full min-w-0 sm:h-56">
                  {({ w, h }) => (
                    <BarChart width={w} height={h} data={productCompare.slice(0, 8)} layout="vertical" margin={{ left: 8, right: 8 }}>
                      <XAxis type="number" hide />
                      <YAxis type="category" dataKey="name" width={88} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(v) => inr(Number(v))} />
                      <Bar dataKey="amount" radius={[0, 6, 6, 0]} isAnimationActive={!reduce}>
                        {productCompare.slice(0, 8).map((p) => (
                          <Cell key={p.product_id} fill="#0f766e" />
                        ))}
                      </Bar>
                    </BarChart>
                  )}
                </ChartBox>
              )}
            </Surface>
            <Surface>
              <h2 className="font-display text-xl">Stock</h2>
              {knownStock.length === 0 ? (
                <div className="mt-3">
                  <EmptyState
                    title="No counted stock to chart"
                    body="Stock charts appear after opening stock or purchases are recorded. Uncounted items are not shown as zero."
                  />
                </div>
              ) : (
                <ul className="mt-4 grid gap-2">
                  {knownStock.slice(0, 8).map((p) => (
                    <li key={p.id} className="flex justify-between gap-3 text-base">
                      <span className="truncate">{p.name}</span>
                      <span className="shrink-0 font-medium">
                        {p.current_stock} {p.unit}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Surface>
          </div>

          <Surface>
            <h2 className="font-display text-xl">Profit</h2>
            <p className="mt-3 text-stone-600">{data.profit_note}</p>
            <p className="mt-2 text-sm text-stone-500">{data.cash_note}</p>
          </Surface>
        </>
      )}
    </div>
  )
}
