import type { ScreeningDecision, CriterionEvaluation } from '@/types'

/**
 * Normalise a decision's `criteria_evaluations` to an array. The backend may return either
 * an array of evaluations or an object keyed by criterion code.
 */
export const normalizeEvaluations = (
  raw: ScreeningDecision['criteria_evaluations'] | null | undefined
): CriterionEvaluation[] => {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return Object.entries(raw).map(([code, evaluation]) => ({
    criterion_code: code,
    criterion_type: evaluation.criterion_type,
    met: evaluation.met,
    confidence: evaluation.confidence,
    reasoning: evaluation.reasoning,
  }))
}

export type DecisionVariant = 'include' | 'exclude' | 'uncertain' | 'outline'

export interface MetStatus {
  text: string
  variant: DecisionVariant
}

export const getMetStatus = (met: boolean | null): MetStatus => {
  if (met === null) return { text: 'Uncertain', variant: 'uncertain' }
  if (met) return { text: 'Met', variant: 'include' }
  return { text: 'Not Met', variant: 'exclude' }
}

/** Badge variant for a screening decision (`include` | `exclude` | `uncertain`). */
export const decisionVariant = (decision: string): DecisionVariant => {
  switch (decision) {
    case 'include':
    case 'included':
      return 'include'
    case 'exclude':
    case 'excluded':
      return 'exclude'
    case 'uncertain':
      return 'uncertain'
    default:
      return 'outline'
  }
}

export const confidenceVariant = (percent: number): 'success' | 'warning' | 'destructive' => {
  if (percent >= 80) return 'success'
  if (percent >= 60) return 'warning'
  return 'destructive'
}
