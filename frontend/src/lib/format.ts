export function inr(n: number) {
  return `₹${n.toLocaleString('en-IN')}`
}

export function shortDate(iso: string) {
  const parts = iso.split('-')
  if (parts.length < 3) return iso
  return `${parts[2]}/${parts[1]}`
}

export function greetingForHour(hour: number) {
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export function addDaysISO(iso: string, n: number) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + n))
  return dt.toISOString().slice(0, 10)
}

export function usePrefersReducedMotion() {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
