<script setup lang="ts">
import { computed } from 'vue'
import type { Agreement } from '@/types'
import Card from '@/components/ui/Card.vue'

interface Props {
  agreement: Agreement
}

const props = defineProps<Props>()

const pct = (v: number | null | undefined): string => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(1)}%`)
const num = (v: number | null | undefined): string => (v === null || v === undefined ? 'n/a' : v.toFixed(2))

const human = computed(() => props.agreement.human_vs_human)
const ai = computed(() => props.agreement.ai_vs_human)
</script>

<template>
  <div class="grid gap-4 md:grid-cols-2">
    <Card class="p-4 space-y-3" data-testid="human-agreement">
      <h4 class="font-semibold">Reviewer agreement</h4>
      <p v-if="!human" class="text-sm text-muted-foreground">
        Requires dual screening (2 required reviewers) and at least two reviewers with decisions.
      </p>
      <dl v-else class="grid grid-cols-3 gap-3 text-center">
        <div>
          <dt class="text-xs text-muted-foreground">Cohen's kappa</dt>
          <dd class="text-2xl font-bold">{{ num(human.cohens_kappa) }}</dd>
        </div>
        <div>
          <dt class="text-xs text-muted-foreground">% agreement</dt>
          <dd class="text-2xl font-bold">{{ pct(human.percent_agreement) }}</dd>
        </div>
        <div>
          <dt class="text-xs text-muted-foreground">Articles</dt>
          <dd class="text-2xl font-bold">{{ human.n_articles }}</dd>
        </div>
      </dl>
    </Card>

    <Card class="p-4 space-y-3" data-testid="ai-agreement">
      <h4 class="font-semibold">AI vs human outcome</h4>
      <p v-if="ai.n_articles === 0" class="text-sm text-muted-foreground">
        No articles with both an AI and a human decision yet.
      </p>
      <template v-else>
        <dl class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div>
            <dt class="text-xs text-muted-foreground">Accuracy</dt>
            <dd class="text-xl font-bold">{{ pct(ai.accuracy) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">Sensitivity</dt>
            <dd class="text-xl font-bold">{{ pct(ai.sensitivity) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">Specificity</dt>
            <dd class="text-xl font-bold">{{ pct(ai.specificity) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">Kappa</dt>
            <dd class="text-xl font-bold">{{ num(ai.cohens_kappa) }}</dd>
          </div>
        </dl>
        <p class="text-xs text-muted-foreground">
          {{ ai.n_articles }} articles: TP {{ ai.true_positives }}, FP {{ ai.false_positives }}, TN
          {{ ai.true_negatives }}, FN {{ ai.false_negatives }}. AI uncertain: {{ ai.ai_uncertain }};
          without AI decision: {{ ai.without_ai_decision }}.
        </p>
      </template>
    </Card>
  </div>
</template>
