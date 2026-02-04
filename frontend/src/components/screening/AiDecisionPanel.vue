<script setup lang="ts">
import { computed } from 'vue'
import type { ScreeningDecision, CriterionEvaluation } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Progress from '@/components/ui/Progress.vue'

interface Props {
  decision: ScreeningDecision | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
})

const decisionBadgeVariant = computed(() => {
  if (!props.decision) return 'default'
  switch (props.decision.decision) {
    case 'include':
      return 'default'
    case 'exclude':
      return 'destructive'
    case 'uncertain':
      return 'secondary'
    default:
      return 'default'
  }
})

const decisionBadgeClass = computed(() => {
  if (!props.decision) return ''
  switch (props.decision.decision) {
    case 'include':
      return 'bg-green-600 text-white'
    case 'exclude':
      return 'bg-red-600 text-white'
    case 'uncertain':
      return 'bg-yellow-600 text-white'
    default:
      return ''
  }
})

const confidencePercent = computed(() => {
  if (!props.decision?.confidence_score) return 0
  return Math.round(props.decision.confidence_score * 100)
})

const confidenceVariant = computed(() => {
  const percent = confidencePercent.value
  if (percent >= 80) return 'success'
  if (percent >= 60) return 'warning'
  return 'destructive'
})

const criteriaEvaluations = computed(() => {
  if (!props.decision?.criteria_evaluations) return []

  // Handle both array and object formats
  if (Array.isArray(props.decision.criteria_evaluations)) {
    return props.decision.criteria_evaluations as CriterionEvaluation[]
  }

  // Convert object format to array
  return Object.entries(props.decision.criteria_evaluations).map(([code, evaluation]) => ({
    criterion_code: code,
    criterion_type: evaluation.criterion_type,
    met: evaluation.met,
    confidence: evaluation.confidence,
    reasoning: evaluation.reasoning,
  })) as CriterionEvaluation[]
})

const getMetStatusBadge = (met: boolean | null) => {
  if (met === null) return { text: 'Uncertain', class: 'bg-yellow-600 text-white' }
  if (met) return { text: 'Met', class: 'bg-green-600 text-white' }
  return { text: 'Not Met', class: 'bg-red-600 text-white' }
}

const getCriterionTypeClass = (type: string) => {
  if (type === 'inclusion') return 'text-green-600'
  if (type === 'exclusion') return 'text-red-600'
  return 'text-muted-foreground'
}

const inclusionEvaluations = computed(() => {
  return criteriaEvaluations.value.filter((e) => e.criterion_type === 'inclusion')
})

const exclusionEvaluations = computed(() => {
  return criteriaEvaluations.value.filter((e) => e.criterion_type === 'exclusion')
})
</script>

<template>
  <Card class="p-6">
    <div class="space-y-4">
      <div class="flex items-center gap-2">
        <h3 class="text-lg font-semibold">AI Screening Result</h3>
        <Badge variant="outline" class="text-xs">AI-Generated</Badge>
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
          <Badge :class="decisionBadgeClass" class="text-sm px-3 py-1 capitalize">
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
          <h4 class="text-sm font-semibold text-red-600">Primary Exclusion Reason</h4>
          <p class="text-sm text-muted-foreground">{{ decision.primary_exclusion_reason }}</p>
        </div>

        <!-- Criteria Evaluations -->
        <div v-if="criteriaEvaluations.length > 0" class="space-y-4">
          <h4 class="text-sm font-semibold">Criteria Evaluations</h4>

          <!-- Inclusion Criteria -->
          <div v-if="inclusionEvaluations.length > 0" class="space-y-2">
            <h5 class="text-xs font-semibold text-green-600 uppercase tracking-wide">
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
                    <Badge :class="getMetStatusBadge(evaluation.met).class" class="text-xs">
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
            <h5 class="text-xs font-semibold text-red-600 uppercase tracking-wide">
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
                    <Badge :class="getMetStatusBadge(evaluation.met).class" class="text-xs">
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
