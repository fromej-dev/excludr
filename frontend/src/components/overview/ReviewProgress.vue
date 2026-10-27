<script setup lang="ts">
import { computed } from 'vue'
import type { ScreeningStats } from '@/types'
import Card from '@/components/ui/Card.vue'

interface Props {
  stats: ScreeningStats | null
  /** Full texts ready to screen for the signed-in user (adds to the "retrieved" count); null when unknown. */
  pendingFullText: number | null
}

const props = defineProps<Props>()

type Tone = 'neutral' | 'ai' | 'include' | 'exclude' | 'uncertain'

interface Step {
  key: string
  label: string
  count: number
  note?: string
  tone: Tone
}

const total = computed(() => props.stats?.total_articles ?? 0)

const steps = computed<Step[]>(() => {
  const s = props.stats
  if (!s) return []
  return [
    { key: 'imported', label: 'Imported', count: s.total_articles, tone: 'neutral' },
    { key: 'ta', label: 'Title/abstract screened', count: s.screened_title_abstract, tone: 'ai' },
    {
      key: 'ft-retrieved',
      label: 'Full text retrieved',
      count: s.screened_full_text + (props.pendingFullText ?? 0),
      note: s.awaiting_full_text > 0 ? `${s.awaiting_full_text} awaiting` : undefined,
      tone: 'ai',
    },
    { key: 'ft', label: 'Full text screened', count: s.screened_full_text, tone: 'ai' },
  ]
})

const outcomes = computed(() => {
  const s = props.stats
  if (!s) return []
  return [
    { key: 'included', label: 'Included', count: s.included, tone: 'include' as Tone },
    { key: 'excluded', label: 'Excluded', count: s.excluded, tone: 'exclude' as Tone },
    { key: 'uncertain', label: 'Uncertain', count: s.uncertain, tone: 'uncertain' as Tone },
  ]
})

const barClass: Record<Tone, string> = {
  neutral: 'bg-muted-foreground/50',
  ai: 'bg-ai',
  include: 'bg-include',
  exclude: 'bg-exclude',
  uncertain: 'bg-uncertain',
}
const chipClass: Record<Tone, string> = {
  neutral: 'bg-secondary text-secondary-foreground',
  ai: 'bg-ai-soft text-ai-soft-foreground',
  include: 'bg-include-soft text-include-soft-foreground',
  exclude: 'bg-exclude-soft text-exclude-soft-foreground',
  uncertain: 'bg-uncertain-soft text-uncertain-soft-foreground',
}

const pct = (n: number): string => (total.value > 0 ? `${Math.min(100, Math.round((n / total.value) * 100))}%` : '0%')
</script>

<template>
  <Card class="p-5" data-testid="review-progress">
    <h2 class="text-lg font-semibold">Progress</h2>
    <div v-if="!stats" class="mt-3 h-24 animate-pulse rounded bg-muted" role="status" aria-label="Loading progress" />
    <p v-else-if="total === 0" class="mt-2 text-sm text-muted-foreground">
      No articles yet. Progress appears here once you import articles.
    </p>
    <template v-else>
      <ol class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <li v-for="(step, i) in steps" :key="step.key" :data-testid="`progress-${step.key}`">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-sm font-medium"><span class="text-muted-foreground">{{ i + 1 }}.</span> {{ step.label }}</span>
          </div>
          <p class="mt-1 text-2xl font-bold tabular-nums">
            {{ step.count }}<span class="text-sm font-normal text-muted-foreground"> / {{ total }}</span>
          </p>
          <div
            class="mt-1 h-2 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            :aria-label="step.label"
            :aria-valuenow="step.count"
            aria-valuemin="0"
            :aria-valuemax="total"
          >
            <div class="h-full rounded-full" :class="barClass[step.tone]" :style="{ width: pct(step.count) }" />
          </div>
          <p v-if="step.note" class="mt-1 text-xs text-muted-foreground">{{ step.note }}</p>
        </li>
      </ol>

      <div class="mt-5 border-t pt-4">
        <p class="text-sm font-medium"><span class="text-muted-foreground">5.</span> Final outcome</p>
        <div class="mt-2 flex h-3 overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <div v-for="o in outcomes" :key="o.key" :class="barClass[o.tone]" :style="{ width: pct(o.count) }" />
        </div>
        <ul class="mt-3 flex flex-wrap gap-2">
          <li
            v-for="o in outcomes"
            :key="o.key"
            class="rounded-full px-3 py-1 text-sm font-medium"
            :class="chipClass[o.tone]"
            :data-testid="`progress-${o.key}`"
          >
            {{ o.label }} <strong class="tabular-nums">{{ o.count }}</strong>
          </li>
        </ul>
      </div>
    </template>
  </Card>
</template>
