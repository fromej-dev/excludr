<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { formatPrice } from '@/stores/billing'
import { formatCount, formatUsd } from '@/utils/format'
import { getErrorMessage } from '@/utils/errors'
import type { AdminOverview } from '@/types'
import Card from '@/components/ui/Card.vue'

const admin = useAdminStore()
const data = ref<AdminOverview | null>(null)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    data.value = await admin.overview()
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not load the overview')
  }
})

/** First day of this month (UTC), as the AI usage page's start date. */
const monthStart = () => new Date().toISOString().slice(0, 8) + '01'

const tiles = computed(() => {
  const d = data.value
  if (!d) return []
  return [
    {
      label: 'Revenue this month',
      value: formatPrice(d.revenue_month_cents, d.currency),
      note: `${formatCount(d.payments_month)} payments · ${formatPrice(d.revenue_total_cents, d.currency)} all time, after refunds`,
    },
    {
      label: 'Active passes',
      value: formatCount(d.active_passes),
      note: `${formatCount(d.expiring_30d)} end within 30 days`,
      link: { name: 'admin-projects', query: { state: 'expiring' } },
    },
    {
      label: 'Users',
      value: formatCount(d.users_total),
      note: `${formatCount(d.users_new_30d)} new in the last 30 days`,
      link: { name: 'admin-users' },
    },
    {
      label: 'Projects',
      value: formatCount(d.projects_total),
      note: 'All reviews, free and paid',
      link: { name: 'admin-projects' },
    },
    {
      label: 'AI full-text screenings this month',
      value: formatCount(d.ai_fulltext_month),
      note: 'Main AI cost driver; includes re-screens',
    },
    {
      label: 'AI title/abstract screenings this month',
      value: formatCount(d.ai_title_abstract_month),
      note: 'Cheap; capped as fair use',
    },
    {
      label: 'AI tokens this month',
      value: formatCount(d.ai_tokens_month),
      note: `About ${formatUsd(d.ai_cost_month_usd)} · see AI usage`,
      link: { name: 'admin-ai-usage', query: { group_by: 'project', start: monthStart() } },
    },
  ]
})
</script>

<template>
  <div>
    <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{{ error }}</p>
    <p v-else-if="!data" class="text-muted-foreground">Loading...</p>
    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="admin-overview">
      <Card v-for="tile in tiles" :key="tile.label" class="p-5">
        <p class="text-sm text-muted-foreground">{{ tile.label }}</p>
        <p class="mt-2 text-3xl font-bold tabular-nums">{{ tile.value }}</p>
        <p class="mt-1 text-xs text-muted-foreground">
          <router-link v-if="tile.link" :to="tile.link" class="hover:text-primary hover:underline">
            {{ tile.note }}
          </router-link>
          <template v-else>{{ tile.note }}</template>
        </p>
      </Card>
    </div>
  </div>
</template>
