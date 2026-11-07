import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiClientError } from '../api/client'
import { fetchDashboard, type DashboardResponse } from '../api/analytics'

type Preset = 'today' | 'yesterday' | '7d' | '30d' | 'custom'

function addDaysISO(iso: string, n: number) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + n))
  return dt.toISOString().slice(0, 10)
}

function inr(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

function shortDate(iso: string) {
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}

function matchPreset(from: string, to: string, today: string, yesterday: string): Preset {
  if (!from || !to) return 'custom'
  if (from === to && from === today) return 'today'
  if (from === to && from === yesterday) return 'yesterday'
  if (to === today && from === addDaysISO(today, -6)) return '7d'
  if (to === today && from === addDaysISO(today, -29)) return '30d'
  return 'custom'
}

export function Dashboard() {
  const [from, setFrom] = useState(() => new URLSearchParams(window.location.search).get('from') ?? '')
  const [to, setTo] = useState(() => new URLSearchParams(window.location.search).get('to') ?? '')
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const dash =
        from && to ? await fetchDashboard(from, to) : await fetchDashboard()
      setData(dash)
      if (!from || !to) {
        setFrom(dash.period.from)
        setTo(dash.period.to)
      }
    } catch (err) {
      setData(null)
      setError(err instanceof ApiClientError ? err.message : 'Could not load dashboard.')
    } finally {
      setLoading(false)
    }
  }, [from, to])

  useEffect(() => {
    void load()
  }, [load])

  const kolkataToday = data?.today.date
  const kolkataYesterday = data?.yesterday.date
  const activePreset = data
    ? matchPreset(data.period.from, data.period.to, data.today.date, data.yesterday.date)
    : 'custom'

  function applyPreset(next: Preset) {
    if (!kolkataToday || !kolkataYesterday) return
    if (next === 'today') {
      setFrom(kolkataToday)
      setTo(kolkataToday)
    } else if (next === 'yesterday') {
      setFrom(kolkataYesterday)
      setTo(kolkataYesterday)
    } else if (next === '7d') {
      setFrom(addDaysISO(kolkataToday, -6))
      setTo(kolkataToday)
    } else if (next === '30d') {
      setFrom(addDaysISO(kolkataToday, -29))
      setTo(kolkataToday)
    }
  }

  const chartData = useMemo(
    () =>
      (data?.trend ?? []).map((row) => ({
        ...row,
        label: shortDate(row.date),
      })),
    [data],
  )

  const periodHasSales = (data?.period.transactions ?? 0) > 0

  return (
    <section className="grid min-w-0 gap-6">
      <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm sm:p-5">
        <p className="text-sm font-medium text-stone-500">Dates use Asia/Kolkata</p>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
          {(['today', 'yesterday', '7d', '30d'] as const).map((key) => (
            <button
              key={key}
              type="button"
              className={`min-h-12 min-w-0 w-full overflow-hidden rounded-xl px-2 text-sm font-medium sm:w-auto sm:px-4 sm:text-base ${
                activePreset === key ? 'bg-amber-800 text-white' : 'border border-stone-300 bg-stone-50'
              }`}
              onClick={() => applyPreset(key)}
            >
              {key === '7d' ? '7 days' : key === '30d' ? '30 days' : key === 'today' ? 'Today' : 'Yesterday'}
            </button>
          ))}
        </div>
        <div className="mt-4 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="min-w-0 text-sm font-medium text-stone-600">
            From
            <input
              className="mt-1 min-h-12 w-full min-w-0 rounded-xl border border-stone-300 px-3 text-base"
              type="date"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value)
              }}
            />
          </label>
          <label className="min-w-0 text-sm font-medium text-stone-600">
            To
            <input
              className="mt-1 min-h-12 w-full min-w-0 rounded-xl border border-stone-300 px-3 text-base"
              type="date"
              value={to}
              onChange={(e) => {
                setTo(e.target.value)
              }}
            />
          </label>
        </div>
        {data && (
          <p className="mt-3 break-words text-sm text-stone-500">
            Showing {data.period.from} to {data.period.to}. Flask today is {data.today.date}.
          </p>
        )}
      </div>

      {loading && <p className="text-lg">Loading shop numbers…</p>}
      {error && (
        <p className="text-lg text-red-800" role="alert">
          {error}
        </p>
      )}

      {data && (
        <>
          <p className="text-sm leading-relaxed text-stone-600">
            {data.cash_note} {data.profit_note}
          </p>
          <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Today's sales" value={inr(data.today.total_amount)} sub={`${data.today.transactions} bills · ${data.today.date}`} accent />
            <Stat label="Yesterday" value={inr(data.yesterday.total_amount)} sub={`${data.yesterday.transactions} bills · ${data.yesterday.date}`} />
            <Stat label="Period sales" value={inr(data.period.total_amount)} sub={`${data.period.from} → ${data.period.to}`} accent />
            <Stat label="Bills in period" value={String(data.period.transactions)} sub="Recorded bills, not cash" />
          </div>

          <div className="min-w-0 max-w-full overflow-hidden rounded-2xl border border-stone-200 bg-white p-3 shadow-sm sm:p-6">
            <h3 className="text-lg font-semibold sm:text-xl">Sales trend</h3>
            <p className="mt-1 text-sm text-stone-500">Daily recorded sales (₹)</p>
            {!periodHasSales ? (
              <p className="mt-6 text-lg text-stone-600">No sales in this period.</p>
            ) : (
              <TrendChart data={chartData} />
            )}
          </div>

          <div className="grid min-w-0 gap-4 lg:grid-cols-2">
            <Card title="Best sellers" subtitle="Highest recorded sale amount">
              {data.best_sellers.length === 0 ? (
                <Empty text="No product sales yet." />
              ) : (
                <ul className="grid gap-3">
                  {data.best_sellers.map((p, i) => (
                    <li key={p.product_id} className="flex min-w-0 items-baseline justify-between gap-3 text-base sm:text-lg">
                      <span className="min-w-0 truncate">
                        <span className="mr-2 text-stone-400">{i + 1}.</span>
                        {p.name}
                      </span>
                      <span className="shrink-0 font-medium">
                        {p.quantity} {p.unit} · {inr(p.amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Low stock" subtitle="At or below your threshold">
              {data.low_stock.length === 0 ? (
                <Empty text="No low-stock alerts." />
              ) : (
                <ul className="grid gap-3">
                  {data.low_stock.map((p) => (
                    <li
                      key={p.id}
                      className="flex min-w-0 items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-3 py-3"
                    >
                      <span className="min-w-0 truncate font-medium text-red-900">{p.name}</span>
                      <span className="shrink-0 rounded-full bg-red-800 px-3 py-1 text-sm text-white">
                        {p.current_stock} {p.unit}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card title="Inventory" subtitle="Active products only">
            {data.inventory.length === 0 ? (
              <Empty text="No active products." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[280px] text-left text-base">
                  <thead>
                    <tr className="border-b border-stone-200 text-sm text-stone-500">
                      <th className="py-2 pr-3 font-medium">Item</th>
                      <th className="py-2 pr-3 font-medium">On hand</th>
                      <th className="py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.inventory.map((p) => (
                      <tr key={p.id} className="border-b border-stone-100">
                        <td className="py-3 pr-3">{p.name}</td>
                        <td className="py-3 pr-3 whitespace-nowrap">
                          {p.current_stock} {p.unit}
                        </td>
                        <td className="py-3">
                          {p.low_stock ? (
                            <span className="rounded-full bg-red-100 px-2 py-1 text-sm text-red-800">Low</span>
                          ) : (
                            <span className="rounded-full bg-emerald-100 px-2 py-1 text-sm text-emerald-800">OK</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Product sales" subtitle="This date range">
            {data.by_product.length === 0 ? (
              <Empty text="Nothing sold in this period." />
            ) : (
              <ul className="grid gap-3">
                {data.by_product.map((p) => (
                  <li key={p.product_id} className="flex min-w-0 justify-between gap-3 text-base sm:text-lg">
                    <span className="min-w-0 truncate">{p.name}</span>
                    <span className="shrink-0 font-medium">{inr(p.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </section>
  )
}

function TrendChart({
  data,
}: {
  data: Array<{ date: string; label: string; total_amount: number; transactions: number }>
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const apply = () => setWidth(Math.max(1, Math.floor(el.getBoundingClientRect().width)))
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const interval = data.length > 10 ? Math.ceil(data.length / 5) - 1 : 0
  return (
    <div ref={ref} className="mt-4 w-full max-w-full overflow-hidden">
      {width > 0 && (
        <BarChart
          width={width}
          height={256}
          data={data}
          margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
        >
          <CartesianGrid stroke="#e7e5e4" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={interval} padding={{ left: 2, right: 8 }} />
          <YAxis tick={{ fontSize: 10 }} width={32} tickFormatter={(v) => `${v}`} />
          <Tooltip formatter={(v) => inr(Number(v))} labelFormatter={(_, payload) => payload?.[0]?.payload?.date ?? ''} />
          <Bar
            dataKey="total_amount"
            fill="#92400e"
            name="Sales"
            radius={[4, 4, 0, 0]}
            minPointSize={3}
            isAnimationActive={false}
          />
        </BarChart>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string
  sub: string
  accent?: boolean
}) {
  return (
    <div
      className={`min-w-0 rounded-2xl border p-5 shadow-sm ${
        accent ? 'border-amber-200 bg-amber-50' : 'border-stone-200 bg-white'
      }`}
    >
      <p className="text-sm font-medium text-stone-500">{label}</p>
      <p className="mt-2 break-words text-3xl font-semibold tracking-tight sm:text-4xl">{value}</p>
      <p className="mt-2 text-sm text-stone-600">{sub}</p>
    </div>
  )
}

function Card({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl border border-stone-200 bg-white p-4 shadow-sm sm:p-6">
      <h3 className="text-lg font-semibold sm:text-xl">{title}</h3>
      <p className="mt-1 text-sm text-stone-500">{subtitle}</p>
      <div className="mt-4">{children}</div>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <p className="text-lg text-stone-600">{text}</p>
}
