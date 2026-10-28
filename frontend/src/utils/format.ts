/** Short date, e.g. "28 Oct 2026"; "-" when missing. */
export const formatDate = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
    : '-'

export const formatCount = (n: number) => n.toLocaleString('en')

/** Value for an `<input type="date">` from an ISO timestamp. */
export const toDateInput = (value: string) => value.slice(0, 10)
