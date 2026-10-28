<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { formatPrice } from '@/stores/billing'
import { formatDate } from '@/utils/format'
import { getErrorMessage } from '@/utils/errors'
import type { AdminPage, AdminPayment, PaymentStatus } from '@/types'
import Select from '@/components/ui/Select.vue'
import Pager from '@/components/admin/Pager.vue'
import StateBadge from '@/components/admin/StateBadge.vue'

const PAGE_SIZE = 25
const admin = useAdminStore()

const status = ref<string | number>('')
const page = ref(1)
const result = ref<AdminPage<AdminPayment> | null>(null)
const error = ref<string | null>(null)

const statusOptions = [
  { value: '', label: 'All payments' },
  { value: 'paid', label: 'Paid' },
  { value: 'partially_refunded', label: 'Partly refunded' },
  { value: 'refunded', label: 'Refunded' },
]

const kinds: Record<string, string> = { new: 'New pass', renewal: 'Renewal', upgrade: 'Upgrade' }

const load = async () => {
  try {
    error.value = null
    result.value = await admin.payments({
      status: status.value as PaymentStatus | '',
      page: page.value,
      page_size: PAGE_SIZE,
    })
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not load payments')
  }
}

watch(status, () => {
  page.value = 1
  void load()
})
watch(page, load)
onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <Select v-model="status" :options="statusOptions" class="max-w-xs" aria-label="Payment status" />
      <p class="text-xs text-muted-foreground">
        Refunds are made in the Stripe dashboard; they show up here automatically.
      </p>
    </div>
    <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{{ error }}</p>
    <div v-if="result" class="space-y-3">
      <div class="overflow-x-auto rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-medium">Date</th>
              <th class="px-3 py-2 font-medium">Project</th>
              <th class="px-3 py-2 font-medium">Paid by</th>
              <th class="px-3 py-2 font-medium">What</th>
              <th class="px-3 py-2 text-right font-medium">Amount</th>
              <th class="px-3 py-2 font-medium">Status</th>
              <th class="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in result.items" :key="p.id" class="border-t" data-testid="admin-payment-row">
              <td class="px-3 py-2 whitespace-nowrap">{{ formatDate(p.created_at) }}</td>
              <td class="px-3 py-2">
                {{ p.project_name }}
                <span v-if="p.project_id === null" class="text-xs text-muted-foreground">(deleted)</span>
              </td>
              <td class="px-3 py-2">
                <router-link
                  v-if="p.user_id && p.user_email"
                  :to="{ name: 'admin-user', params: { userId: p.user_id } }"
                  class="hover:text-primary hover:underline"
                >
                  {{ p.user_email }}
                </router-link>
                <span v-else class="text-muted-foreground">-</span>
              </td>
              <td class="px-3 py-2">{{ kinds[p.kind] ?? p.kind }} · {{ p.tier }}</td>
              <td class="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                {{ formatPrice(p.amount_cents, p.currency) }}
                <div v-if="p.refunded_cents" class="text-xs text-muted-foreground">
                  −{{ formatPrice(p.refunded_cents, p.currency) }} refunded
                </div>
              </td>
              <td class="px-3 py-2"><StateBadge :state="p.status" /></td>
              <td class="px-3 py-2 text-right">
                <a
                  v-if="p.dashboard_url"
                  :href="p.dashboard_url"
                  target="_blank"
                  rel="noopener"
                  class="text-sm font-medium text-primary hover:underline"
                >
                  Stripe ↗
                </a>
              </td>
            </tr>
            <tr v-if="!result.items.length">
              <td colspan="7" class="px-3 py-6 text-center text-muted-foreground">No payments yet</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager v-model:page="page" :page-size="PAGE_SIZE" :total="result.total" />
    </div>
  </div>
</template>
