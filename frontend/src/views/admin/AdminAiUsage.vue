<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import { formatCount, formatUsd } from '@/utils/format'
import { getErrorMessage } from '@/utils/errors'
import type { AiActivity, AiUsageFilters, AiUsageGroup, AiUsageGroupBy, AiUsageReport } from '@/types'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'

const LIMIT = 100
const admin = useAdminStore()
const route = useRoute()
const router = useRouter()

const groupByOptions: { value: AiUsageGroupBy; label: string }[] = [
  { value: 'project', label: 'Per project' },
  { value: 'user', label: 'Per user' },
  { value: 'article', label: 'Per article' },
  { value: 'stage', label: 'Per stage' },
  { value: 'activity', label: 'Per activity' },
  { value: 'model', label: 'Per model' },
  { value: 'day', label: 'Per day' },
  { value: 'month', label: 'Per month' },
]

const columnLabels: Record<AiUsageGroupBy, string> = {
  project: 'Project',
  user: 'Started by',
  article: 'Article',
  stage: 'Stage',
  activity: 'Activity',
  model: 'Model',
  day: 'Day',
  month: 'Month',
}

const activityLabels: Record<AiActivity, string> = {
  screening_single: 'Single article screening',
  screening_batch: 'Batch screening',
  screening_lookahead: 'Screening lookahead',
}
const stageLabels: Record<string, string> = { title_abstract: 'Title/abstract', full_text: 'Full text' }

const activityOptions = [
  { value: '', label: 'All activities' },
  ...Object.entries(activityLabels).map(([value, label]) => ({ value, label })),
]
const stageOptions = [
  { value: '', label: 'All stages' },
  ...Object.entries(stageLabels).map(([value, label]) => ({ value, label })),
]

const str = (v: unknown) => (typeof v === 'string' ? v : '')
const num = (v: unknown) => (typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : undefined)

// Filters live in the URL so a report can be linked and reloaded.
const groupBy = computed<AiUsageGroupBy>(() => {
  const value = str(route.query.group_by)
  return groupByOptions.some((o) => o.value === value) ? (value as AiUsageGroupBy) : 'project'
})
const filters = computed<AiUsageFilters>(() => ({
  start: str(route.query.start),
  end: str(route.query.end),
  activity: str(route.query.activity) as AiUsageFilters['activity'],
  stage: str(route.query.stage) as AiUsageFilters['stage'],
  model: str(route.query.model),
  project_id: num(route.query.project_id),
  user_id: num(route.query.user_id),
}))

const setQuery = (changes: Record<string, string | number | undefined>) => {
  const query: Record<string, string> = {}
  for (const [k, v] of Object.entries({ ...route.query, ...changes })) {
    if (v !== undefined && v !== null && v !== '') query[k] = String(v)
  }
  void router.replace({ query })
}

const bind = (key: string) =>
  computed<string | number>({
    get: () => str(route.query[key]),
    set: (v) => setQuery({ [key]: v }),
  })
const groupByModel = computed<string | number>({
  get: () => groupBy.value,
  set: (v) => setQuery({ group_by: v }),
})
const start = bind('start')
const end = bind('end')
const activity = bind('activity')
const stage = bind('stage')

const iso = (d: Date) => d.toISOString().slice(0, 10)
const presets = [
  {
    label: 'This month',
    range: () => {
      const now = new Date()
      return [iso(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))), '']
    },
  },
  {
    label: 'Last month',
    range: () => {
      const now = new Date()
      return [
        iso(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1))),
        iso(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 0))),
      ]
    },
  },
  { label: 'Last 30 days', range: () => [iso(new Date(Date.now() - 29 * 86_400_000)), ''] },
  { label: 'All time', range: () => ['', ''] },
]
const applyPreset = (range: () => string[]) => {
  const [s, e] = range()
  setQuery({ start: s, end: e })
}

const scope = computed(() => {
  const parts: { key: string; label: string }[] = []
  if (filters.value.project_id) parts.push({ key: 'project_id', label: `Project #${filters.value.project_id}` })
  if (filters.value.user_id) parts.push({ key: 'user_id', label: `Started by user #${filters.value.user_id}` })
  if (filters.value.model) parts.push({ key: 'model', label: `Model ${filters.value.model}` })
  return parts
})

const report = ref<AiUsageReport | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)
const exporting = ref(false)

const load = async () => {
  loading.value = true
  try {
    error.value = null
    report.value = await admin.aiUsage({ ...filters.value, group_by: groupBy.value, limit: LIMIT })
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not load AI usage')
  } finally {
    loading.value = false
  }
}

const download = async (perGroup: boolean) => {
  exporting.value = true
  try {
    error.value = null
    await admin.exportAiUsage({ ...filters.value, ...(perGroup ? { group_by: groupBy.value } : {}) })
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Export failed')
  } finally {
    exporting.value = false
  }
}

watch(() => route.query, load, { deep: true })
onMounted(load)

const tiles = computed(() => {
  const t = report.value?.totals
  if (!t) return []
  return [
    {
      label: 'Tokens',
      value: formatCount(t.total_tokens),
      note: `${formatCount(t.input_tokens)} in (${formatCount(t.cache_read_tokens)} from cache) · ${formatCount(t.output_tokens)} out`,
    },
    {
      label: 'Estimated cost',
      value: formatUsd(t.cost_usd),
      note: t.unpriced_runs
        ? `${formatCount(t.unpriced_runs)} runs on a model without a price are not included`
        : 'At the model prices when each run was made',
    },
    {
      label: 'AI runs',
      value: formatCount(t.runs),
      note: `${formatCount(t.failed_runs)} failed · ${formatCount(t.requests)} model requests`,
    },
    {
      label: 'Articles',
      value: formatCount(t.articles),
      note: t.articles ? `${formatCount(Math.round(t.total_tokens / t.articles))} tokens per article` : '-',
    },
  ]
})

const share = (g: AiUsageGroup) =>
  report.value?.totals.total_tokens ? (g.total_tokens / report.value.totals.total_tokens) * 100 : 0

const label = (g: AiUsageGroup) => {
  if (groupBy.value === 'activity') return activityLabels[g.key as AiActivity] ?? g.label
  if (groupBy.value === 'stage') return stageLabels[g.key ?? ''] ?? g.label
  return g.label
}

/** Narrow the report to one group: a project's articles, a user's projects. */
const drillDown = (g: AiUsageGroup) => {
  if (g.key === null) return null
  if (groupBy.value === 'project') return () => setQuery({ project_id: g.key!, group_by: 'article' })
  if (groupBy.value === 'user') return () => setQuery({ user_id: g.key!, group_by: 'project' })
  if (groupBy.value === 'model') return () => setQuery({ model: g.key!, group_by: 'project' })
  return null
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-end gap-3">
      <label class="w-40 space-y-1 text-xs text-muted-foreground">
        <span>Group</span>
        <Select v-model="groupByModel" :options="groupByOptions" aria-label="Group by" />
      </label>
      <label class="w-40 space-y-1 text-xs text-muted-foreground">
        <span>From</span>
        <Input v-model="start" type="date" aria-label="From" />
      </label>
      <label class="w-40 space-y-1 text-xs text-muted-foreground">
        <span>To</span>
        <Input v-model="end" type="date" aria-label="To" />
      </label>
      <label class="w-56 space-y-1 text-xs text-muted-foreground">
        <span>Activity</span>
        <Select v-model="activity" :options="activityOptions" aria-label="Activity" />
      </label>
      <label class="w-40 space-y-1 text-xs text-muted-foreground">
        <span>Stage</span>
        <Select v-model="stage" :options="stageOptions" aria-label="Stage" />
      </label>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <Button v-for="p in presets" :key="p.label" size="sm" variant="outline" @click="applyPreset(p.range)">
          {{ p.label }}
        </Button>
        <button
          v-for="s in scope"
          :key="s.key"
          type="button"
          class="rounded-full bg-accent px-3 py-1 text-xs font-medium hover:bg-accent/70"
          :aria-label="`Remove filter ${s.label}`"
          @click="setQuery({ [s.key]: undefined })"
        >
          {{ s.label }} ✕
        </button>
      </div>
      <div class="flex gap-2">
        <Button size="sm" variant="outline" :disabled="exporting" data-testid="export-groups" @click="download(true)">
          Export table (CSV)
        </Button>
        <Button size="sm" variant="outline" :disabled="exporting" data-testid="export-runs" @click="download(false)">
          Export all runs (CSV)
        </Button>
      </div>
    </div>

    <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{{ error }}</p>
    <p v-else-if="!report" class="text-muted-foreground">Loading...</p>

    <template v-if="report">
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="ai-usage-totals">
        <Card v-for="tile in tiles" :key="tile.label" class="p-5">
          <p class="text-sm text-muted-foreground">{{ tile.label }}</p>
          <p class="mt-2 text-2xl font-bold tabular-nums">{{ tile.value }}</p>
          <p class="mt-1 text-xs text-muted-foreground">{{ tile.note }}</p>
        </Card>
      </div>

      <div class="overflow-x-auto rounded-lg border" :class="{ 'opacity-60': loading }">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-medium">{{ columnLabels[groupBy] }}</th>
              <th class="px-3 py-2 text-right font-medium">Runs</th>
              <th class="px-3 py-2 text-right font-medium">Articles</th>
              <th class="px-3 py-2 text-right font-medium">Input tokens</th>
              <th class="px-3 py-2 text-right font-medium">Output tokens</th>
              <th class="px-3 py-2 text-right font-medium">Total tokens</th>
              <th class="px-3 py-2 text-right font-medium">Est. cost</th>
              <th class="w-32 px-3 py-2 font-medium">Share</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in report.groups" :key="g.key ?? 'none'" class="border-t" data-testid="ai-usage-row">
              <td class="max-w-md px-3 py-2">
                <button
                  v-if="drillDown(g)"
                  type="button"
                  class="text-left font-medium hover:text-primary hover:underline"
                  @click="drillDown(g)!()"
                >
                  {{ label(g) }}
                </button>
                <span v-else class="line-clamp-2" :class="{ 'text-muted-foreground': g.key === null }">{{ label(g) }}</span>
                <router-link
                  v-if="groupBy === 'user' && g.key"
                  :to="{ name: 'admin-user', params: { userId: g.key } }"
                  class="ml-2 text-xs text-muted-foreground hover:text-primary hover:underline"
                >
                  profile
                </router-link>
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ formatCount(g.runs) }}
                <div v-if="g.failed_runs" class="text-xs text-muted-foreground">{{ formatCount(g.failed_runs) }} failed</div>
              </td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(g.articles) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(g.input_tokens) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(g.output_tokens) }}</td>
              <td class="px-3 py-2 text-right font-medium tabular-nums">{{ formatCount(g.total_tokens) }}</td>
              <td class="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                {{ formatUsd(g.cost_usd) }}<span v-if="g.unpriced_runs" title="Includes runs without a price">*</span>
              </td>
              <td class="px-3 py-2">
                <div class="h-2 rounded-full bg-muted" :title="`${share(g).toFixed(1)}% of tokens`">
                  <div class="h-2 rounded-full bg-primary" :style="{ width: `${share(g)}%` }" />
                </div>
              </td>
            </tr>
            <tr v-if="!report.groups.length">
              <td colspan="8" class="px-3 py-6 text-center text-muted-foreground">No AI usage in this period</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs text-muted-foreground">
        <template v-if="report.group_count > report.groups.length">
          Showing the {{ formatCount(report.groups.length) }} largest of {{ formatCount(report.group_count) }}; the
          export has them all.
        </template>
        Every AI run counts, failed ones included. Costs are estimates from token counts, not invoices. Dates are in UTC.
      </p>
    </template>
  </div>
</template>
