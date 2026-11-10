import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../../api/client'
import { confirmIntent } from '../../api/intent'
import {
  fetchSale,
  fetchSales,
  postSaleCancel,
  postSaleCorrection,
  postSaleReturn,
  type SaleRow,
} from '../../api/shop'
import { inr } from '../../lib/format'
import { subscribeShopRecords } from '../../lib/shopRecords'
import { exportUrl } from '../../lib/downloadCsv'
import { EmptyState, PageTitle, Surface } from '../ui'

export function SalesPage() {
  const [rows, setRows] = useState<SaleRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [billId, setBillId] = useState('')
  const [open, setOpen] = useState<SaleRow | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const [lineKey, setLineKey] = useState('')
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState('')
  const sessionRef = useRef(`sales-${crypto.randomUUID()}`)

  const loadGen = useRef(0)
  const load = useCallback(async (silent = false) => {
    const gen = ++loadGen.current
    if (!silent) setLoading(true)
    setError(null)
    try {
      const data = await fetchSales({
        from: from || undefined,
        to: to || undefined,
        id: billId || undefined,
      })
      if (gen !== loadGen.current) return
      setRows(data.sales)
    } catch (err) {
      if (gen !== loadGen.current) return
      setError(err instanceof ApiClientError ? err.message : 'Could not load sales.')
    } finally {
      if (gen === loadGen.current && !silent) setLoading(false)
    }
  }, [from, to, billId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => subscribeShopRecords(() => void load(true)), [load])

  const openBill = async (id: number) => {
    setError(null)
    try {
      const data = await fetchSale(id)
      setOpen(data.sale)
      setLineKey(data.sale.lines?.[0]?.line_key || '')
      setConfirmText('')
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Could not load bill.')
    }
  }

  const mutate = async (kind: 'correct' | 'return' | 'cancel') => {
    if (!open) return
    if (confirmText !== 'CONFIRM') {
      setError('Type CONFIRM to save a correction, return, or cancellation.')
      return
    }
    try {
      const session_id = sessionRef.current
      let proposed: { pending_id?: string; needs_confirmation?: boolean }
      if (kind === 'cancel') {
        proposed = await postSaleCancel(open.id, { session_id })
      } else if (kind === 'return') {
        proposed = await postSaleReturn(open.id, {
          line_key: lineKey,
          quantity: Number(qty),
          session_id,
        })
      } else {
        proposed = await postSaleCorrection(open.id, {
          line_key: lineKey,
          quantity: qty ? Number(qty) : undefined,
          unit_price: price ? Number(price) : undefined,
          session_id,
        })
      }
      if (!proposed.pending_id) {
        setError('Confirmation was not created.')
        return
      }
      await confirmIntent(proposed.pending_id, session_id)
      await openBill(open.id)
      await load()
      setConfirmText('')
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Could not update the bill.')
    }
  }

  return (
    <div className="grid min-w-0 gap-6 pb-8">
      <PageTitle
        kicker="Sales"
        title="Recorded bills"
        sub="Original amounts stay on the bill. Net recorded sales subtract returns and cancellations. These figures are not cash received."
      />
      <a
        className="inline-flex min-h-11 w-fit items-center rounded-2xl bg-teal-800 px-4 text-sm font-medium text-white"
        href={exportUrl('sales', { from: from || undefined, to: to || undefined, date: billId ? undefined : undefined })}
        download
      >
        Download CSV
      </a>
      <Surface>
        <form
          className="flex flex-wrap gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            void load()
          }}
        >
          <label className="grid text-sm">
            From
            <input className="min-h-11 rounded-lg border px-2" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="grid text-sm">
            To
            <input className="min-h-11 rounded-lg border px-2" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="grid text-sm">
            Bill ID
            <input className="min-h-11 rounded-lg border px-2" value={billId} onChange={(e) => setBillId(e.target.value)} />
          </label>
          <button className="min-h-11 self-end rounded-xl bg-stone-800 px-4 text-white" type="submit">
            Filter
          </button>
        </form>
      </Surface>
      {loading && <p>Loading sales…</p>}
      {error && (
        <p className="text-red-800" role="alert">
          {error}
        </p>
      )}
      {!loading && rows.length === 0 && (
        <EmptyState title="No bills yet" body="When you confirm a sale by voice or API, it will show up here." />
      )}
      {rows.length > 0 && (
        <Surface>
          <ul className="grid gap-3">
            {rows.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className="flex min-h-12 w-full min-w-0 justify-between gap-3 border-b border-stone-100 py-3 text-left"
                  onClick={() => void openBill(s.id)}
                >
                  <span className="min-w-0">
                    <span className="block font-medium">
                      {s.transaction_date} · Bill #{s.id} {s.status === 'cancelled' ? '(cancelled)' : ''}
                    </span>
                    <span className="text-sm text-stone-500">
                      Original {inr(s.total_amount)}
                      {s.financials ? ` · Net ${inr(s.financials.net_recorded)}` : ''}
                    </span>
                  </span>
                  <span className="shrink-0 font-semibold">{inr(s.financials?.net_recorded ?? s.total_amount)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Surface>
      )}
      {open && (
        <Surface>
          <h2 className="text-xl font-semibold">Bill #{open.id}</h2>
          <p className="text-sm text-stone-600">
            Status {open.status || 'open'}. Cash received/refunded is not recorded.
          </p>
          <ul className="mt-3 grid gap-2">
            {(open.lines || []).map((ln) => (
              <li key={ln.line_key}>
                {ln.product_name}: remaining {ln.remaining_quantity} {ln.unit} (sold {ln.effective_quantity}, returned{' '}
                {ln.returned_quantity}) @ {inr(ln.unit_price)}
              </li>
            ))}
          </ul>
          {open.financials && (
            <p className="mt-2 text-sm">
              Original {inr(open.financials.original_recorded)} · Corrections {inr(open.financials.correction_adjustment)} ·
              Returns {inr(open.financials.return_amount)} · Net {inr(open.financials.net_recorded)}
            </p>
          )}
          {open.status !== 'cancelled' && (
            <div className="mt-4 grid gap-3">
              <label className="grid text-sm">
                Line
                <select className="min-h-11 rounded-lg border px-2" value={lineKey} onChange={(e) => setLineKey(e.target.value)}>
                  {(open.lines || []).map((ln) => (
                    <option key={ln.line_key} value={ln.line_key}>
                      {ln.product_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid text-sm">
                Quantity
                <input className="min-h-11 rounded-lg border px-2" value={qty} onChange={(e) => setQty(e.target.value)} />
              </label>
              <label className="grid text-sm">
                Unit price (₹)
                <input className="min-h-11 rounded-lg border px-2" value={price} onChange={(e) => setPrice(e.target.value)} />
              </label>
              <label className="grid text-sm">
                Type CONFIRM
                <input className="min-h-11 rounded-lg border px-2" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
              </label>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="min-h-11 rounded-xl border px-4" onClick={() => void mutate('correct')}>
                  Save correction
                </button>
                <button type="button" className="min-h-11 rounded-xl border px-4" onClick={() => void mutate('return')}>
                  Record return
                </button>
                <button type="button" className="min-h-11 rounded-xl border px-4 text-red-800" onClick={() => void mutate('cancel')}>
                  Cancel bill
                </button>
              </div>
            </div>
          )}
        </Surface>
      )}
    </div>
  )
}
