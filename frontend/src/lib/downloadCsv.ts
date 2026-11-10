export function exportUrl(kind: 'sales' | 'inventory' | 'analytics', params?: Record<string, string | undefined>) {
  const q = new URLSearchParams()
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v) q.set(k, v)
    }
  }
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return `/api/exports/${kind}.csv${suffix}`
}
