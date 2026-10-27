import axios from 'axios'

/** Extract a human-readable message from an unknown thrown value (FastAPI `detail` aware). */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail: unknown = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d: unknown) =>
          typeof d === 'object' && d !== null && 'msg' in d ? String((d as { msg: unknown }).msg) : ''
        )
        .filter(Boolean)
      if (msgs.length) return msgs.join('; ')
    }
  }
  return fallback
}

export function getErrorStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined
}
