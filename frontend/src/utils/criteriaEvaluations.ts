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

export interface MetStatus {
  text: string
  class: string
}

export const getMetStatus = (met: boolean | null): MetStatus => {
  if (met === null) return { text: 'Uncertain', class: 'bg-yellow-600 text-white' }
  if (met) return { text: 'Met', class: 'bg-green-600 text-white' }
  return { text: 'Not Met', class: 'bg-red-600 text-white' }
}

export const decisionBadgeClass = (decision: string): string => {
  switch (decision) {
    case 'include':
      return 'bg-green-600 text-white'
    case 'exclude':
      return 'bg-red-600 text-white'
    case 'uncertain':
      return 'bg-yellow-600 text-white'
    default:
      return ''
  }
}

export const confidenceVariant = (percent: number): 'success' | 'warning' | 'destructive' => {
  if (percent >= 80) return 'success'
  if (percent >= 60) return 'warning'
  return 'destructive'
}
