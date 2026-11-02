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

/**
 * p-value for display: `p < 0.001`, otherwise 3 significant digits. Digits are added until the rounded
 * value is on the same side of `alpha` as `p`, so a p below alpha never reads as alpha or more.
 */
export const formatP = (p: number, alpha?: number): string => {
  if (p < 0.001) return 'p < 0.001'
  let text = String(Number(p.toPrecision(3)))
  for (let digits = 3; digits <= 10; digits++) {
    const rounded = Number(p.toPrecision(digits))
    text = String(rounded)
    if (alpha === undefined || p < alpha ? rounded < (alpha ?? Infinity) : rounded >= alpha) break
  }
  return `p = ${text}`
}

/** Recall target (fraction) as a percent with up to 2 decimals, e.g. 0.95 -> `95%`. */
export const formatPercent = (fraction: number): string => `${Math.round(fraction * 10000) / 100}%`
