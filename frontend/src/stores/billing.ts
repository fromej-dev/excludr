import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { BillingStatus } from '@/types'

/** Format an amount in cents, e.g. 4900 -> "€49". */
export const formatPrice = (cents: number, currency = 'eur') =>
  new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: currency.toUpperCase(),
    minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100)

const PENDING_KEY = 'excludr_pending_checkout'

/** The current project's review pass and AI screening usage. */
export const useBillingStore = defineStore('billing', () => {
  const { get, post } = useApi()

  const status = ref<BillingStatus | null>(null)
  const projectId = ref<number | null>(null)
  const checkoutTier = ref<string | null>(null)
  const error = ref<string | null>(null)

  const fetchStatus = async (id: number) => {
    if (projectId.value !== id) status.value = null
    projectId.value = id
    try {
      const res = await get<BillingStatus>(`/projects/${id}/billing`)
      if (projectId.value === id) status.value = res
      return res
    } catch {
      return null
    }
  }

  /** Send the browser to Stripe Checkout for a pass. Returns false on failure. */
  const startCheckout = async (id: number, tier: string) => {
    checkoutTier.value = tier
    error.value = null
    try {
      const res = await post<{ url: string }>(`/projects/${id}/billing/checkout`, { tier })
      try {
        sessionStorage.setItem(PENDING_KEY, JSON.stringify({ projectId: id, tier }))
      } catch {
        // Storage unavailable: the return page then just waits for any active pass
      }
      window.location.assign(res.url)
      return true
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Could not start the payment')
      checkoutTier.value = null
      return false
    }
  }

  /** The tier bought for this project before leaving for Stripe (read once). */
  const takePendingTier = (id: number): string | null => {
    try {
      const raw = sessionStorage.getItem(PENDING_KEY)
      sessionStorage.removeItem(PENDING_KEY)
      const pending = raw ? (JSON.parse(raw) as { projectId: number; tier: string }) : null
      return pending?.projectId === id ? pending.tier : null
    } catch {
      return null
    }
  }

  return { status, checkoutTier, error, fetchStatus, startCheckout, takePendingTier }
})
