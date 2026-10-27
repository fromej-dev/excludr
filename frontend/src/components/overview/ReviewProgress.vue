<script setup lang="ts">
import { computed } from 'vue'
import type { ScreeningStats } from '@/types'
import Card from '@/components/ui/Card.vue'

interface Props {
  stats: ScreeningStats | null
}

const props = defineProps<Props>()

type Tone = 'neutral' | 'ai' | 'include' | 'exclude' | 'uncertain'

interface Step {
  key: string
  label: string
  count: number
  /** What `count` is out of. */
  of: number
  note?: string
  tone: Tone
}

const total = computed(() => props.stats?.total_articles ?? 0)

const plural = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`
const join = (parts: Array<string | false>): string | undefined => parts.filter(Boolean).join(' · ') || undefined

const steps = computed<Step[]>(() => {
  const s = props.stats
  if (!s) return []
  return [
    {
      key: 'imported',
      label: 'Entered screening',
      count: s.title_abstract_total,
      of: s.total_articles,
      note: join([s.imported_not_started > 0 && `${s.imported_not_started} imported, not started`]),
      tone: 'neutral',
    },
    {
      key: 'ta',
      label: 'Title/abstract screened',
      count: s.title_abstract_completed,
      of: s.title_abstract_total,
      note: join([
        s.title_abstract_completed > 0 && `${s.full_text_eligible} passed · ${s.excluded_title_abstract} excluded`,
        s.awaiting_screening > 0 && `${s.awaiting_screening} open`,
      ]),
      tone: 'ai',
    },
    {
      key: 'ft-retrieved',
      label: 'Full text retrieved',
      count: s.full_text_retrieved,
      of: s.full_text_eligible,
      note: join([s.awaiting_full_text > 0 && `${s.awaiting_full_text} awaiting retrieval`]),
      tone: 'ai',
    },
    {
      key: 'ft',
      label: 'Full text screened',
      count: s.full_text_completed,
      of: s.full_text_eligible,
      note: join([
        s.full_text_completed > 0 && `${s.included} included · ${s.excluded_full_text} excluded`,
        s.awaiting_full_text_screening > 0 && `${plural(s.awaiting_full_text_screening, 'full text', 'full texts')} to screen`,
      ]),
      tone: 'ai',
    },
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

/** Articles still open somewhere in the pipeline (not included or excluded yet). */
const open = computed(() => {
  const s = props.stats
  return s ? s.total_articles - s.included - s.excluded : 0
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

const pct = (n: number, of: number = total.value): string =>
  of > 0 ? `${Math.min(100, Math.round((n / of) * 100))}%` : '0%'
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
            <span data-testid="progress-count">{{ step.count }}</span
            ><span class="text-sm font-normal text-muted-foreground">
              / <span data-testid="progress-of">{{ step.of }}</span></span
            >
          </p>
          <div
            class="mt-1 h-2 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            :aria-label="step.label"
            :aria-valuenow="step.count"
            aria-valuemin="0"
            :aria-valuemax="step.of"
          >
            <div class="h-full rounded-full" :class="barClass[step.tone]" :style="{ width: pct(step.count, step.of) }" />
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
        <p class="mt-2 text-xs text-muted-foreground" data-testid="progress-outcome-note">
          {{ stats.excluded_title_abstract }} excluded at title/abstract · {{ stats.excluded_full_text }} at full text<template
            v-if="open > 0"
          >
            · {{ open }} still open</template
          ><template v-if="stats.uncertain > 0"> (incl. {{ stats.uncertain }} marked uncertain)</template>
        </p>
      </div>
    </template>
  </Card>
</template>
