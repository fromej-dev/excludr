<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { QueueOrderMode, ScreeningStage, ScreeningStats } from '@/types'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Progress from '@/components/ui/Progress.vue'
import { formatDate, formatP, formatPercent } from '@/utils/format'

interface Props {
  stage: Exclude<ScreeningStage, 'completed'>
  stats: ScreeningStats | null
  queueOrder: QueueOrderMode | null
  randomStartRemaining: number
  isOwner: boolean
  /** The pass has expired: nothing can be applied. */
  readOnly?: boolean
  /** From the full stopping-rule status: met and there are records to close. */
  canApply?: boolean
}

const props = withDefaults(defineProps<Props>(), { readOnly: false, canApply: false })
const route = useRoute()
const emit = defineEmits<{ apply: [] }>()

const rule = computed(() => props.stats?.stopping_rule ?? null)
const notScreened = computed(() => props.stats?.not_screened_stopping_rule ?? 0)

const visible = computed(
  () =>
    props.stage === 'title_abstract' &&
    (rule.value !== null || props.queueOrder === 'ranked' || props.queueOrder === 'random_start')
)

const statistical = computed(() => !!rule.value?.enabled && rule.value.rule_type === 'statistical')
const showStreak = computed(
  () => !statistical.value && !!rule.value?.enabled && rule.value.threshold !== null
)
const target = computed(() => formatPercent(rule.value?.recall_target ?? 0.95))
const alphaText = computed(() => String(rule.value?.alpha ?? 0.05))
const recallText = computed(() => {
  const r = rule.value
  if (!r) return ''
  if (r.test_reason === 'no_relevant') return 'Recall test starts after the first include'
  if (r.test_reason === 'no_sample') {
    return 'Recall test: no records screened since the last import or rule change'
  }
  if (r.p_value === null || r.p_value === undefined) return `Recall ≥ ${target.value} not yet shown`
  return `Recall ≥ ${target.value} not yet shown (${formatP(r.p_value)}, needs < ${alphaText.value})`
})
const streakPct = computed(() =>
  rule.value?.threshold ? Math.min(100, (rule.value.consecutive_excludes / rule.value.threshold) * 100) : 0
)
const met = computed(() => !!rule.value?.met && (props.stats?.awaiting_screening ?? 0) > 0)
const showApplied = computed(() => !!rule.value?.applied_at && notScreened.value > 0)
</script>

<template>
  <div
    v-if="visible"
    class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-card px-3 py-2 text-sm"
    :class="met ? 'border-ai/60 bg-ai-soft' : ''"
    :role="met ? 'status' : undefined"
    data-testid="queue-status"
  >
    <span data-testid="queue-badge">
      <Badge
        v-if="queueOrder === 'ranked'"
        variant="ai"
        title="Records the model predicts as most relevant come first. The ranking is retrained as you screen."
      >
        Ranked by relevance
      </Badge>
      <Badge
        v-else-if="queueOrder === 'random_start'"
        variant="secondary"
        title="The first records are shown in random order so the model learns from an unbiased sample."
      >
        Random start · {{ randomStartRemaining }} to go
      </Badge>
    </span>

    <div v-if="showStreak" class="flex max-w-full shrink-0 items-center gap-2 whitespace-nowrap" data-testid="stopping-streak">
      <div class="w-20 shrink-0"><Progress :value="streakPct" size="sm" /></div>
      <span aria-live="polite" class="whitespace-nowrap tabular-nums">
        {{ rule?.consecutive_excludes }} / {{ rule?.threshold }} consecutive excludes
      </span>
    </div>

    <span
      v-if="statistical && !met"
      class="tabular-nums"
      aria-live="polite"
      data-testid="stopping-recall"
    >
      {{ recallText }}
    </span>

    <div v-if="met" class="flex flex-wrap items-center gap-3" data-testid="stopping-rule-met">
      <span>
        <strong>Stopping rule met.</strong>
        <template v-if="statistical">
          <span data-testid="stopping-recall">
            Recall below {{ target }} rejected ({{ formatP(rule?.p_value ?? 0) }} &lt; {{ alphaText }}).
          </span>
        </template>
        <template v-else>{{ rule?.threshold }} consecutive records were excluded.</template>
      </span>
      <template v-if="isOwner">
        <Button
          v-if="!readOnly && canApply"
          size="sm"
          data-testid="apply-rule-open"
          @click="emit('apply')"
        >
          Apply stopping rule…
        </Button>
        <span v-else-if="readOnly" class="text-muted-foreground">
          The pass has expired, so the rule cannot be applied.
        </span>
      </template>
      <span v-else class="text-muted-foreground">The owner can close the remaining unscreened records.</span>
    </div>

    <p v-if="showApplied" class="text-muted-foreground" data-testid="stopping-applied">
      Stopping rule applied {{ formatDate(rule?.applied_at) }} · {{ notScreened }} not screened
      <router-link
        v-if="isOwner"
        :to="{ name: 'project-articles', params: { id: route.params.id }, query: { status: 'not_screened' } }"
        class="ml-1 font-medium text-primary hover:underline"
      >
        View
      </router-link>
    </p>
  </div>
</template>
