import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { useProjectsStore } from './projects'
import { useProjectStatsStore } from './projectStats'
import { useProjectNavStore } from './projectNav'
import { useMembersStore } from './members'
import type {
  ApplyStoppingRuleRequest,
  ApplyStoppingRuleResult,
  RerankResponse,
  ReopenNotScreenedResult,
  StoppingRuleStatus,
} from '@/types'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'

export type RuleOutcome<T> = { ok: true; result: T } | { ok: false; status?: number; message: string }

/** Safety net: stop showing "Re-ranking…" if the websocket event never arrives. */
const RERANK_TIMEOUT_MS = 60_000

/** Status of the stopping rule and ranking of the open project, plus the owner actions. */
export const useStoppingRuleStore = defineStore('stoppingRule', () => {
  const { get, post } = useApi()

  const projectId = ref<number | null>(null)
  const status = ref<StoppingRuleStatus | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** Running since the owner pressed Re-rank; cleared by ranking_updated / ranking_failed / 60 s. */
  const reranking = ref(false)

  let seq = 0
  let applied = 0
  let rerankTimer: ReturnType<typeof setTimeout> | null = null

  const clearRerank = () => {
    reranking.value = false
    if (rerankTimer) clearTimeout(rerankTimer)
    rerankTimer = null
  }

  const reset = () => {
    seq++
    applied = seq
    projectId.value = null
    status.value = null
    loading.value = false
    error.value = null
    clearRerank()
  }

  const fetch = async (id: number) => {
    if (projectId.value !== id) reset()
    projectId.value = id
    const mine = ++seq
    loading.value = true
    try {
      const result = await get<StoppingRuleStatus>(`/projects/${id}/screening/stopping-rule`)
      if (projectId.value === id && mine > applied) {
        applied = mine
        status.value = result
        error.value = null
      }
    } catch (err: unknown) {
      if (projectId.value === id && mine > applied) {
        applied = mine
        error.value = getErrorMessage(err, "Couldn't load ranking status")
      }
    } finally {
      if (projectId.value === id && mine === seq) loading.value = false
    }
  }

  const apply = async (
    id: number,
    body: ApplyStoppingRuleRequest
  ): Promise<RuleOutcome<ApplyStoppingRuleResult>> => {
    try {
      const result = await post<ApplyStoppingRuleResult>(
        `/projects/${id}/screening/apply-stopping-rule`,
        body
      )
      await fetch(id)
      return { ok: true, result }
    } catch (err: unknown) {
      return {
        ok: false,
        status: getErrorStatus(err),
        message: getErrorMessage(err, 'Failed to apply the stopping rule'),
      }
    }
  }

  const reopen = async (id: number): Promise<RuleOutcome<ReopenNotScreenedResult>> => {
    try {
      const result = await post<ReopenNotScreenedResult>(`/projects/${id}/screening/reopen-not-screened`)
      if (projectId.value === id) await fetch(id)
      return { ok: true, result }
    } catch (err: unknown) {
      return {
        ok: false,
        status: getErrorStatus(err),
        message: getErrorMessage(err, 'Failed to reopen the records'),
      }
    }
  }

  const rerank = async (id: number): Promise<RerankResponse | null> => {
    error.value = null
    reranking.value = true
    if (rerankTimer) clearTimeout(rerankTimer)
    rerankTimer = setTimeout(clearRerank, RERANK_TIMEOUT_MS)
    try {
      return await post<RerankResponse>(`/projects/${id}/screening/rerank`)
    } catch (err: unknown) {
      clearRerank()
      error.value = getErrorMessage(err, 'Failed to start re-ranking')
      return null
    }
  }

  return { projectId, status, loading, error, reranking, fetch, apply, reopen, rerank, reset, clearRerank }
})

/** After the rule is applied or reverted: stats, project (applied date), and the queue counts. */
export async function refreshAfterRuleChange(id: number): Promise<void> {
  const members = useMembersStore()
  await Promise.all([
    useProjectStatsStore().fetch(id),
    useProjectsStore().fetchProject(id),
    members.canReview ? useProjectNavStore().refreshScreening(id) : Promise.resolve(),
  ])
}
