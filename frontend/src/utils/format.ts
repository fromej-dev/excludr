/** Short date, e.g. "28 Oct 2026"; "-" when missing. */
export const formatDate = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
    : '-'

export const formatCount = (n: number) => n.toLocaleString('en')

/** Value for an `<input type="date">` from an ISO timestamp. */
export const toDateInput = (value: string) => value.slice(0, 10)

/** US dollars; small amounts (AI costs) keep four decimals. */
export const formatUsd = (value: number) =>
  value.toLocaleString('en', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: value !== 0 && Math.abs(value) < 1 ? 4 : 2,
  })

/** p-value for display: `p < 0.001`, two decimals from 0.01, otherwise 2 significant digits. */
export const formatP = (p: number): string => {
  if (p < 0.001) return 'p < 0.001'
  const text = p >= 0.01 ? p.toFixed(2) : String(Number(p.toPrecision(2)))
  return `p = ${text}`
}

/** Recall target (fraction) as a whole percent, e.g. 0.95 -> `95%`. */
export const formatPercent = (fraction: number): string => `${Math.round(fraction * 1000) / 10}%`
