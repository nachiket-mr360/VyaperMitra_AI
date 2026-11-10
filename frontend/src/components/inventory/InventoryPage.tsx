import { useCallback, useEffect, useState } from 'react'
import { ApiClientError } from '../../api/client'
import { fetchProducts, type Product } from '../../api/shop'
import { subscribeShopRecords } from '../../lib/shopRecords'
import { exportUrl } from '../../lib/downloadCsv'
import { EmptyState, PageTitle, Surface } from '../ui'

export function InventoryPage() {
  const [rows, setRows] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const data = await fetchProducts()
      setRows(data.products)
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Could not load inventory.')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => subscribeShopRecords(() => void load(true)), [load])

  const known = rows.filter((p) => p.stock_known !== false && p.current_stock != null)

  return (
    <div className="grid min-w-0 gap-6 pb-8">
      <PageTitle
        kicker="Inventory"
        title="What you have on hand"
        sub="Stock is only shown when it has been counted. Voice and planner still work the same way."
      />
      <a
        className="inline-flex min-h-11 w-fit items-center rounded-2xl bg-teal-800 px-4 text-sm font-medium text-white"
        href={exportUrl('inventory')}
        download
      >
        Download CSV
      </a>
      {loading && <p>Loading inventory…</p>}
      {error && (
        <p className="text-red-800" role="alert">
          {error}
        </p>
      )}
      {!loading && rows.length === 0 && (
        <EmptyState title="No products yet" body="Add items through your usual purchase flow. This list stays empty until then." />
      )}
      {rows.length > 0 && (
        <Surface>
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
                {rows.map((p) => (
                  <tr key={p.id} className="border-b border-stone-100">
                    <td className="py-3 pr-3">{p.name}</td>
                    <td className="py-3 pr-3 whitespace-nowrap">
                      {p.stock_known === false || p.current_stock == null
                        ? 'Not counted'
                        : `${p.current_stock} ${p.unit}`}
                    </td>
                    <td className="py-3">
                      {p.low_stock ? (
                        <span className="rounded-full bg-red-100 px-2 py-1 text-sm text-red-800">Low</span>
                      ) : known.some((k) => k.id === p.id) ? (
                        <span className="rounded-full bg-emerald-100 px-2 py-1 text-sm text-emerald-800">OK</span>
                      ) : (
                        <span className="text-sm text-stone-500">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Surface>
      )}
    </div>
  )
}
