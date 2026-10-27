<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatPrice, useBillingStore } from '@/stores/billing'
import { useWebSocketStore } from '@/stores/websocket'
import type { BillingUsage, PassOption } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Progress from '@/components/ui/Progress.vue'

interface Props {
  projectId: number
  /** Only the owner can buy a pass. */
  canBuy: boolean
}

const props = defineProps<Props>()
const route = useRoute()
const router = useRouter()
const billing = useBillingStore()
const wsStore = useWebSocketStore()

const status = computed(() => billing.status)

const POLL_INTERVAL_MS = 2000
const POLL_ATTEMPTS = 15
let pollTimer: ReturnType<typeof setTimeout> | null = null

/** After Stripe sends the owner back, wait for the webhook to apply the bought tier. */
const waitForPayment = async (tier: string | null, attempt = 0) => {
  const res = await billing.fetchStatus(props.projectId)
  if (res?.active && (!tier || res.plan === tier)) {
    wsStore.addNotification('Payment received. Your review pass is active.', 'success')
    return
  }
  if (attempt >= POLL_ATTEMPTS) {
    wsStore.addNotification(
      'Payment received. Activation is taking longer than usual; refresh in a minute.',
      'info'
    )
    return
  }
  pollTimer = setTimeout(() => waitForPayment(tier, attempt + 1), POLL_INTERVAL_MS)
}

onMounted(() => {
  const result = route.query.billing
  if (result) {
    const { billing: _ignored, ...query } = route.query
    router.replace({ query })
  }
  if (result === 'success') {
    void waitForPayment(billing.takePendingTier(props.projectId))
    return
  }
  if (result === 'cancelled') {
    billing.takePendingTier(props.projectId)
    wsStore.addNotification('Payment cancelled. Nothing was charged.', 'info')
  }
  void billing.fetchStatus(props.projectId)
})

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})

const percent = (usage: BillingUsage) =>
  usage.limit ? Math.min(100, Math.round((usage.used / usage.limit) * 100)) : 0

const meterVariant = (usage: BillingUsage) => {
  const p = percent(usage)
  return p >= 100 ? 'destructive' : p >= 80 ? 'warning' : 'default'
}

const expires = computed(() =>
  status.value?.expires_at
    ? new Date(status.value.expires_at).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null
)

const badge = computed(() => {
  if (!status.value) return null
  if (status.value.read_only) return { text: 'Expired', variant: 'destructive' as const }
  if (status.value.active) return { text: 'Active', variant: 'default' as const }
  return { text: 'Free', variant: 'secondary' as const }
})

const optionText = (o: PassOption) => {
  const price = formatPrice(o.amount_cents, status.value?.currency)
  const size = `${o.fulltext_limit.toLocaleString('en')} full texts`
  if (o.kind === 'upgrade') return `Upgrade to ${size} · ${price}`
  if (o.kind === 'renewal') return `Renew, ${size} · ${price}`
  return `${size} · ${price}`
}

const buy = async (tier: string) => {
  const ok = await billing.startCheckout(props.projectId, tier)
  if (!ok) wsStore.addNotification(billing.error ?? 'Could not start the payment', 'error')
}
</script>

<template>
  <Card v-if="status?.billing_enabled" class="p-6 space-y-4" data-testid="plan-card">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="font-semibold">Plan</h3>
          <Badge v-if="badge" :variant="badge.variant" data-testid="plan-badge">{{ badge.text }}</Badge>
        </div>
        <p class="mt-1 text-sm text-muted-foreground" data-testid="plan-label">
          {{ status.plan_label }}
          <template v-if="expires && status.active"> · active until {{ expires }}</template>
          <template v-else-if="expires"> · expired on {{ expires }}</template>
        </p>
      </div>
    </div>

    <div v-if="!status.read_only" class="space-y-1" data-testid="fulltext-usage">
      <div class="flex justify-between text-sm">
        <span>AI-screened full texts</span>
        <span class="font-medium">
          {{ status.full_text.used.toLocaleString('en') }} / {{ status.full_text.limit.toLocaleString('en') }}
        </span>
      </div>
      <Progress :value="percent(status.full_text)" :variant="meterVariant(status.full_text)" />
      <p v-if="status.full_text.scope === 'account'" class="text-xs text-muted-foreground">
        Free allowance, shared by all of the owner's projects without a pass.
      </p>
    </div>

    <p v-if="status.read_only" class="text-sm">
      The pass for this review has expired, so the project is read-only. Everything stays
      viewable and exportable. Renew to keep screening.
    </p>

    <div v-if="status.options.length" class="space-y-2">
      <p class="text-sm font-medium">
        {{ status.active ? 'Need more?' : status.read_only ? 'Renew this review' : 'Buy a review pass' }}
        <span class="font-normal text-muted-foreground">
          {{
            status.active
              ? 'Pay only the difference; the pass keeps its end date.'
              : 'One-off payment, 12 months, includes dual screening.'
          }}
        </span>
      </p>
      <div v-if="canBuy" class="flex flex-wrap gap-2">
        <Button
          v-for="option in status.options"
          :key="option.tier"
          size="sm"
          :variant="option === status.options[0] ? 'default' : 'outline'"
          :disabled="billing.checkoutTier !== null"
          :data-testid="`buy-${option.tier}`"
          @click="buy(option.tier)"
        >
          {{ billing.checkoutTier === option.tier ? 'Opening checkout...' : optionText(option) }}
        </Button>
      </div>
      <p v-else class="text-xs text-muted-foreground">Only the project owner can buy a pass.</p>
    </div>
  </Card>
</template>
