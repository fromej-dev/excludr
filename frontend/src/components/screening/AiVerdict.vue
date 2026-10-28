<script setup lang="ts">
import { computed } from 'vue'
import type { ScreeningDecision } from '@/types'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Progress from '@/components/ui/Progress.vue'
import { decisionVariant, confidenceVariant } from '@/utils/criteriaEvaluations'

interface Props {
  decision: ScreeningDecision | null
  loading?: boolean
  /** Reviewer role or higher: may run the AI on this article. */
  canRun?: boolean
  /** Queued by the lookahead; the verdict arrives over the websocket. */
  queued?: boolean
  /** Why background AI screening is off for this session (quiet note), if it is. */
  unavailable?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  canRun: true,
  queued: false,
  unavailable: null,
})
const emit = defineEmits<{ screen: [] }>()
/** "Auto-screen ahead" toggle; the toggle is only shown when bound (reviewers). */
const autoAhead = defineModel<boolean | undefined>('autoAhead', { default: undefined })

const confidencePercent = computed(() => Math.round((props.decision?.confidence_score ?? 0) * 100))
</script>

<template>
  <section class="space-y-2" data-testid="ai-verdict">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <h2 class="text-sm font-semibold">AI verdict</h2>
        <Badge variant="ai" class="text-[10px]">AI-Generated</Badge>
      </div>
      <Button v-if="!decision && !loading && !queued && canRun" variant="outline" size="sm" @click="emit('screen')">
        Screen with AI
      </Button>
    </div>

    <p v-if="loading" class="text-sm text-muted-foreground">AI is analyzing the article...</p>
    <p
      v-else-if="queued"
      class="flex items-center gap-2 text-sm text-muted-foreground"
      role="status"
      data-testid="ai-pending"
    >
      <span
        aria-hidden="true"
        class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
      />
      AI screening…
    </p>
    <p v-else-if="!decision" class="text-sm text-muted-foreground">No AI screening result yet.</p>

    <template v-else>
      <div class="flex items-center gap-3">
        <Badge 
          :variant="decisionVariant(decision.decision)"
          class="px-3 py-1 text-sm capitalize">
          {{ decision.decision }}
        </Badge>
        <div class="flex flex-1 items-center gap-2">
          <Progress :value="confidencePercent" :variant="confidenceVariant(confidencePercent)" size="sm" />
          <span class="whitespace-nowrap text-xs font-semibold">{{ confidencePercent }}%</span>
        </div>
      </div>
      <details v-if="decision.reasoning || decision.primary_exclusion_reason" class="text-sm">
        <summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Summary</summary>
        <p v-if="decision.reasoning" class="mt-1 leading-relaxed text-muted-foreground">{{ decision.reasoning }}</p>
        <p v-if="decision.primary_exclusion_reason && decision.decision === 'exclude'" class="mt-1 text-exclude-soft-foreground">
          {{ decision.primary_exclusion_reason }}
        </p>
      </details>
    </template>

    <p v-if="unavailable && autoAhead" class="text-xs text-muted-foreground" data-testid="ai-unavailable">
      AI screening unavailable: {{ unavailable }}
    </p>
    <label
      v-if="canRun && autoAhead !== undefined"
      class="flex w-fit cursor-pointer items-center gap-2 text-xs text-muted-foreground"
      title="Screen the current article and the next two in your queue with AI in the background"
    >
      <input
        v-model="autoAhead"
        type="checkbox"
        class="h-3.5 w-3.5 rounded border-input accent-primary"
        data-testid="ai-auto-ahead"
      />
      Auto-screen ahead
    </label>
  </section>
</template>
