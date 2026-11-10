import { apiGet, apiPostJson } from './client'
import type { StockRow } from './analytics'

export type Product = {
  id: number
  name: string
  unit: string
  current_stock: number | null
  stock_known?: boolean
  low_stock_threshold?: number
  low_stock?: boolean
  active?: boolean
}

export type SaleLine = {
  line_key: string
  product_id: number
  product_name?: string
  unit?: string
  original_quantity: number
  effective_quantity: number
  returned_quantity: number
  remaining_quantity: number
  unit_price: number
}

export type SaleFinancials = {
  original_recorded: number
  correction_adjustment: number
  return_amount: number
  cancellation_reversal: number
  net_recorded: number
  cash_received: null
  cash_refunded: null
  outstanding: null
}

export type SaleRow = {
  id: number
  transaction_date: string
  total_amount: number
  payment_status?: string
  status?: string
  items?: Array<{ product_id: number; quantity: number; line_total: number; product_name?: string; name?: string }>
  lines?: SaleLine[]
  financials?: SaleFinancials
}

export function fetchProducts() {
  return apiGet<{ ok: boolean; products: Product[] }>('/api/products')
}

export function fetchStock() {
  return apiGet<{ ok: boolean; stock?: StockRow[]; products?: StockRow[] }>('/api/stock')
}

export function fetchSales(params?: { date?: string; from?: string; to?: string; id?: string }) {
  const q = new URLSearchParams()
  if (params?.date) q.set('date', params.date)
  if (params?.from) q.set('from', params.from)
  if (params?.to) q.set('to', params.to)
  if (params?.id) q.set('id', params.id)
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return apiGet<{ ok: boolean; sales: SaleRow[] }>(`/api/sales${suffix}`)
}

export function fetchSale(id: number) {
  return apiGet<{ ok: boolean; sale: SaleRow }>(`/api/sales/${id}`)
}

export function postSaleCorrection(id: number, body: Record<string, unknown>) {
  return apiPostJson<{ ok: boolean; pending_id?: string; needs_confirmation?: boolean; sale?: SaleRow }>(
    `/api/sales/${id}/corrections`,
    body,
  )
}

export function postSaleReturn(id: number, body: Record<string, unknown>) {
  return apiPostJson<{ ok: boolean; pending_id?: string; needs_confirmation?: boolean; sale?: SaleRow }>(
    `/api/sales/${id}/returns`,
    body,
  )
}

export function postSaleCancel(id: number, body: Record<string, unknown>) {
  return apiPostJson<{ ok: boolean; pending_id?: string; needs_confirmation?: boolean; sale?: SaleRow }>(
    `/api/sales/${id}/cancel`,
    body,
  )
}
