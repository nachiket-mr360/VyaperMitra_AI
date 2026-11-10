import { useCallback, useEffect, useState } from 'react'
import { ApiClientError } from '../../api/client'
import { fetchDashboard, type DashboardResponse } from '../../api/analytics'
import { inr } from '../../lib/format'
import { subscribeShopRecords } from '../../lib/shopRecords'
import { exportUrl } from '../../lib/downloadCsv'
import { EmptyState, PageTitle, Surface } from '../ui'

export function InsightsPage() {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setData(await fetchDashboard())
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Could not load insights.')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => subscribeShopRecords(() => void load()), [load])

  const slow =
    data?.inventory.filter((p) => {
      const sold = data.by_product.find((s) => s.product_id === p.id)
      return p.stock_known !== false && (!sold || sold.amount === 0)
    }) ?? []

  return (
    <div className="grid min-w-0 gap-6 pb-8">
      <PageTitle
        kicker="Business insights"
        title="What the records support"
        sub="Suggestions stay within your sales and stock history. Profit is omitted until purchase cost is complete."
      />
      <a
        className="inline-flex min-h-11 w-fit items-center rounded-2xl bg-teal-800 px-4 text-sm font-medium text-white"
        href={exportUrl('analytics', data ? { from: data.period.from, to: data.period.to } : undefined)}
        download
      >
        Download CSV
      </a>
      {error && (
        <p className="text-red-800" role="alert">
          {error}
        </p>
      )}
      {data && (
        <>
          <Surface>
            <h2 className="font-display text-xl">Period snapshot</h2>
            <p className="mt-2 text-3xl font-semibold">{inr(data.period.total_amount)}</p>
            <p className="mt-1 text-sm text-stone-500">
              {data.period.transactions} bills from {data.period.from} to {data.period.to}
            </p>
          </Surface>
          <Surface>
            <h2 className="font-display text-xl">Best sellers</h2>
            {data.best_sellers.length === 0 ? (
              <div className="mt-3">
                <EmptyState title="No product ranking yet" body="Need recorded product sales in this period." />
              </div>
            ) : (
              <ol className="mt-4 grid gap-2">
                {data.best_sellers.map((p, i) => (
                  <li key={p.product_id} className="flex justify-between gap-3">
                    <span>
                      {i + 1}. {p.name}
                    </span>
                    <span>{inr(p.amount)}</span>
                  </li>
                ))}
              </ol>
            )}
          </Surface>
          <Surface>
            <h2 className="font-display text-xl">Quiet products</h2>
            {data.period.transactions < 5 ? (
              <div className="mt-3">
                <EmptyState
                  title="Not enough history"
                  body="Slow-moving products are listed after more bills are recorded, so we do not guess."
                />
              </div>
            ) : slow.length === 0 ? (
              <p className="mt-3 text-stone-600">Every counted item has some sales in this window.</p>
            ) : (
              <ul className="mt-3 grid gap-2">
                {slow.map((p) => (
                  <li key={p.id}>{p.name}</li>
                ))}
              </ul>
            )}
          </Surface>
          <Surface>
            <h2 className="font-display text-xl">Profit & cash</h2>
            <p className="mt-3 text-stone-600">{data.profit_note}</p>
            <p className="mt-2 text-sm text-stone-500">{data.cash_note}</p>
          </Surface>
        </>
      )}
    </div>
  )
}
