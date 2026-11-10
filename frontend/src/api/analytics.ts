import { apiGet } from './client'

export type ProductSaleRow = {
  product_id: number
  name: string
  unit: string
  quantity: number
  amount: number
}

export type StockRow = {
  id: number
  name: string
  unit: string
  current_stock: number | null
  stock_known?: boolean
  low_stock_threshold?: number
  low_stock?: boolean
}

export type DashboardResponse = {
  ok: boolean
  timezone: string
  cash_note: string
  profit_note: string
  today: { date: string; total_amount: number; transactions: number }
  yesterday: { date: string; total_amount: number; transactions: number }
  period: { from: string; to: string; total_amount: number; transactions: number }
  trend: Array<{ date: string; total_amount: number; transactions: number }>
  best_sellers: ProductSaleRow[]
  by_product: ProductSaleRow[]
  inventory: StockRow[]
  low_stock: StockRow[]
}

export function fetchDashboard(from?: string, to?: string) {
  const q = new URLSearchParams()
  if (from) q.set('from', from)
  if (to) q.set('to', to)
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return apiGet<DashboardResponse>(`/api/analytics/dashboard${suffix}`)
}
