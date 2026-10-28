<script setup lang="ts">
import { computed } from 'vue'
import type { ScreeningDecision } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Progress from '@/components/ui/Progress.vue'
import {
  normalizeEvaluations,
  getMetStatus as getMetStatusBadge,
  decisionVariant,
  confidenceVariant as confidenceVariantFor,
} from '@/utils/criteriaEvaluations'

interface Props {
  decision: ScreeningDecision | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
})

const decisionBadgeVariant = computed(() =>
  props.decision ? decisionVariant(props.decision.decision) : 'outline'
)

const confidencePercent = computed(() => {
  if (!props.decision?.confidence_score) return 0
  return Math.round(props.decision.confidence_score * 100)
})

const confidenceVariant = computed(() => confidenceVariantFor(confidencePercent.value))

/** Which stage the verdict was made at: a title/abstract verdict says nothing about the full text. */
const stageLabel = computed(() =>
  props.decision?.stage === 'full_text' ? 'Full text' : props.decision ? 'Title/abstract' : null
)

const criteriaEvaluations = computed(() => normalizeEvaluations(props.decision?.criteria_evaluations))

const inclusionEvaluations = computed(() =>
  criteriaEvaluations.value.filter((e) => e.criterion_type === 'inclusion')
)

const exclusionEvaluations = computed(() =>
  criteriaEvaluations.value.filter((e) => e.criterion_type === 'exclusion')
)
</script>

<template>
  <Card class="p-6">
    <div class="space-y-4">
      <div class="flex items-center gap-2">
        <h3 class="text-lg font-semibold">AI Screening Result</h3>
        <Badge variant="ai" class="text-xs">AI-Generated</Badge>
        <Badge v-if="stageLabel && !loading" variant="outline" class="text-xs" data-testid="ai-decision-stage">
          {{ stageLabel }}
        </Badge>
      </div>

      <!-- Loading State -->
      <div v-if="loading" class="py-8 text-center text-muted-foreground">
        <p>AI is analyzing the article...</p>
      </div>

      <!-- No Decision State -->
      <div v-else-if="!decision" class="py-4 text-center text-muted-foreground">
        <p class="text-sm">No AI screening result available yet.</p>
      </div>

      <!-- Decision Display -->
      <div v-else class="space-y-4">
        <!-- Decision Badge and Confidence -->
        <div class="flex items-center justify-between">
          <Badge :variant="decisionBadgeVariant" class="text-sm px-3 py-1 capitalize">
            {{ decision.decision }}
          </Badge>

          <div class="flex items-center gap-2">
            <span class="text-sm text-muted-foreground">Confidence:</span>
            <span class="text-sm font-semibold">{{ confidencePercent }}%</span>
          </div>
        </div>

        <!-- Confidence Progress Bar -->
        <Progress :value="confidencePercent" :variant="confidenceVariant" size="md" />

        <!-- Overall Reasoning -->
        <div v-if="decision.reasoning" class="space-y-2">
          <h4 class="text-sm font-semibold">Summary</h4>
          <p class="text-sm text-muted-foreground leading-relaxed">{{ decision.reasoning }}</p>
        </div>

        <!-- Primary Exclusion Reason -->
        <div v-if="decision.primary_exclusion_reason && decision.decision === 'exclude'" class="space-y-2">
          <h4 class="text-sm font-semibold text-exclude-soft-foreground">Primary Exclusion Reason</h4>
          <p class="text-sm text-muted-foreground">{{ decision.primary_exclusion_reason }}</p>
        </div>

        <!-- Criteria Evaluations -->
        <div v-if="criteriaEvaluations.length > 0" class="space-y-4">
          <h4 class="text-sm font-semibold">Criteria Evaluations</h4>

          <!-- Inclusion Criteria -->
          <div v-if="inclusionEvaluations.length > 0" class="space-y-2">
            <h5 class="text-xs font-semibold text-include-soft-foreground uppercase tracking-wide">
              Inclusion Criteria
            </h5>
            <div class="space-y-2">
              <div
                v-for="(evaluation, index) in inclusionEvaluations"
                :key="index"
                class="border rounded-lg p-3 space-y-2"
              >
                <div class="flex items-center justify-between">
                  <Badge variant="outline" class="font-mono">
                    {{ evaluation.criterion_code }}
                  </Badge>

                  <div class="flex items-center gap-2">
                    <Badge :variant="getMetStatusBadge(evaluation.met).variant" class="text-xs">
                      {{ getMetStatusBadge(evaluation.met).text }}
                    </Badge>
                    <span class="text-xs text-muted-foreground">
                      {{ Math.round(evaluation.confidence * 100) }}%
                    </span>
                  </div>
                </div>

                <div v-if="evaluation.reasoning" class="text-xs text-muted-foreground leading-relaxed">
                  {{ evaluation.reasoning }}
                </div>
              </div>
            </div>
          </div>

          <!-- Exclusion Criteria -->
          <div v-if="exclusionEvaluations.length > 0" class="space-y-2">
            <h5 class="text-xs font-semibold text-exclude-soft-foreground uppercase tracking-wide">
              Exclusion Criteria
            </h5>
            <div class="space-y-2">
              <div
                v-for="(evaluation, index) in exclusionEvaluations"
                :key="index"
                class="border rounded-lg p-3 space-y-2"
              >
                <div class="flex items-center justify-between">
                  <Badge variant="outline" class="font-mono">
                    {{ evaluation.criterion_code }}
                  </Badge>

                  <div class="flex items-center gap-2">
                    <Badge :variant="getMetStatusBadge(evaluation.met).variant" class="text-xs">
                      {{ getMetStatusBadge(evaluation.met).text }}
                    </Badge>
                    <span class="text-xs text-muted-foreground">
                      {{ Math.round(evaluation.confidence * 100) }}%
                    </span>
                  </div>
                </div>

                <div v-if="evaluation.reasoning" class="text-xs text-muted-foreground leading-relaxed">
                  {{ evaluation.reasoning }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Timestamp -->
        <div class="text-xs text-muted-foreground pt-2 border-t">
          Generated: {{ new Date(decision.created_at).toLocaleString() }}
        </div>
      </div>
    </div>
  </Card>
</template>
