export type VizPoint = { label: string; value: number; value2?: number }

export type VisualizationPayload = {
  type: 'line' | 'bar' | 'hbar' | 'area' | 'comparison'
  title: string
  subtitle?: string
  x_key: string
  y_key: string
  y_label?: string
  unit?: string
  metric: 'recorded_sales_amount' | 'sales_quantity' | 'transaction_count' | 'stock_quantity'
  date_range?: { from?: string | null; to?: string | null }
  points: VizPoint[]
  notes?: string[]
  kpis?: { label: string; value: number }[]
  dashboard?: { page?: string; from?: string | null; to?: string | null }
}

const TYPES = new Set(['line', 'bar', 'hbar', 'area', 'comparison'])
const METRICS = new Set([
  'recorded_sales_amount',
  'sales_quantity',
  'transaction_count',
  'stock_quantity',
])

export function validateVisualization(raw: unknown): VisualizationPayload | null {
  if (!raw || typeof raw !== 'object') return null
  const v = raw as Record<string, unknown>
  if (!TYPES.has(String(v.type))) return null
  if (!METRICS.has(String(v.metric))) return null
  const title = String(v.title || '').trim()
  if (!title) return null
  if (!Array.isArray(v.points) || v.points.length === 0) return null
  const points: VizPoint[] = []
  for (const p of v.points.slice(0, 31)) {
    if (!p || typeof p !== 'object') return null
    const row = p as Record<string, unknown>
    const label = String(row.label || '').trim()
    const value = Number(row.value)
    if (!label || !Number.isFinite(value)) return null
    const item: VizPoint = { label, value }
    if (row.value2 != null) {
      const v2 = Number(row.value2)
      if (!Number.isFinite(v2)) return null
      item.value2 = v2
    }
    points.push(item)
  }
  if (!points.length) return null
  const rng = (v.date_range && typeof v.date_range === 'object' ? v.date_range : {}) as Record<string, unknown>
  const dash = (v.dashboard && typeof v.dashboard === 'object' ? v.dashboard : {}) as Record<string, unknown>
  return {
    type: v.type as VisualizationPayload['type'],
    title,
    subtitle: v.subtitle ? String(v.subtitle) : '',
    x_key: 'label',
    y_key: 'value',
    y_label: v.y_label ? String(v.y_label) : 'Recorded sales (₹)',
    unit: v.unit ? String(v.unit) : 'INR',
    metric: v.metric as VisualizationPayload['metric'],
    date_range: { from: (rng.from as string) || null, to: (rng.to as string) || null },
    points,
    notes: Array.isArray(v.notes) ? v.notes.map(String) : [],
    kpis: Array.isArray(v.kpis)
      ? (v.kpis as unknown[])
          .map((k) => {
            if (!k || typeof k !== 'object') return null
            const row = k as Record<string, unknown>
            const label = String(row.label || '').trim()
            const value = Number(row.value)
            if (!label || !Number.isFinite(value)) return null
            return { label, value }
          })
          .filter((x): x is { label: string; value: number } => !!x)
      : [],
    dashboard: {
      page: dash.page ? String(dash.page) : 'insights',
      from: (dash.from as string) || null,
      to: (dash.to as string) || null,
    },
  }
}

export function vizFingerprint(v: VisualizationPayload) {
  return `${v.type}|${v.title}|${v.points.map((p) => `${p.label}:${p.value}`).join(',')}`
}
