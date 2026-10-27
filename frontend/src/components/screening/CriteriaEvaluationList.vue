<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Criterion, CriterionEvaluation } from '@/types'
import Badge from '@/components/ui/Badge.vue'
import { getMetStatus } from '@/utils/criteriaEvaluations'

interface Props {
  inclusion: Criterion[]
  exclusion: Criterion[]
  /** Normalised AI evaluations (see `normalizeEvaluations`). */
  evaluations: CriterionEvaluation[]
}

const props = defineProps<Props>()

const byCode = computed(() => new Map(props.evaluations.map((e) => [e.criterion_code, e])))

/** Evaluations that match none of the current criteria (e.g. criteria were edited since). */
const orphaned = computed(() => {
  const known = new Set([...props.inclusion, ...props.exclusion].map((c) => c.code))
  return props.evaluations.filter((e) => !known.has(e.criterion_code))
})

const open = ref<Set<string>>(new Set())
const toggle = (code: string) => {
  const next = new Set(open.value)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  open.value = next
}

const groups = computed(() => [
  { key: 'inclusion', title: 'Inclusion Criteria', titleClass: 'text-green-600', items: props.inclusion },
  { key: 'exclusion', title: 'Exclusion Criteria', titleClass: 'text-red-600', items: props.exclusion },
])
</script>

<template>
  <div class="space-y-4" data-testid="criteria-list">
    <section v-for="g in groups" :key="g.key" class="space-y-2">
      <h3 :class="['text-xs font-semibold uppercase tracking-wide', g.titleClass]">{{ g.title }}</h3>
      <p v-if="g.items.length === 0" class="text-xs text-muted-foreground">None defined.</p>
      <ul class="space-y-2">
        <li
          v-for="c in g.items"
          :key="c.id"
          class="rounded-md border p-2 text-sm"
          :data-testid="`criterion-${c.code}`"
        >
          <div class="flex items-start gap-2">
            <Badge variant="outline" class="mt-0.5 shrink-0 font-mono">{{ c.code }}</Badge>
            <span class="min-w-0 flex-1 break-words">{{ c.description }}</span>
            <div v-if="byCode.get(c.code)" class="flex shrink-0 items-center gap-1.5">
              <Badge :class="getMetStatus(byCode.get(c.code)!.met).class" class="text-[11px]">
                {{ getMetStatus(byCode.get(c.code)!.met).text }}
              </Badge>
              <span class="text-xs text-muted-foreground">
                {{ Math.round(byCode.get(c.code)!.confidence * 100) }}%
              </span>
            </div>
          </div>
          <template v-if="byCode.get(c.code)?.reasoning">
            <button
              type="button"
              class="mt-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              :aria-expanded="open.has(c.code)"
              @click="toggle(c.code)"
            >
              {{ open.has(c.code) ? 'Hide AI reasoning' : 'Show AI reasoning' }}
            </button>
            <p v-if="open.has(c.code)" class="mt-1 text-xs leading-relaxed text-muted-foreground">
              {{ byCode.get(c.code)!.reasoning }}
            </p>
          </template>
        </li>
      </ul>
    </section>

    <section v-if="orphaned.length > 0" class="space-y-2">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Other AI evaluations</h3>
      <ul class="space-y-2">
        <li v-for="e in orphaned" :key="e.criterion_code" class="rounded-md border p-2 text-sm">
          <div class="flex items-center gap-2">
            <Badge variant="outline" class="font-mono">{{ e.criterion_code }}</Badge>
            <Badge :class="getMetStatus(e.met).class" class="text-[11px]">{{ getMetStatus(e.met).text }}</Badge>
            <span class="text-xs text-muted-foreground">{{ Math.round(e.confidence * 100) }}%</span>
          </div>
          <p v-if="e.reasoning" class="mt-1 text-xs text-muted-foreground">{{ e.reasoning }}</p>
        </li>
      </ul>
    </section>
  </div>
</template>
