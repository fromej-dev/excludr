import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Conflict, Criterion, PaginatedResponse, Article } from '@/types'

type CountedStage = 'title_abstract' | 'full_text'

export interface NavRefreshOptions {
  canReview: boolean
  isOwner: boolean
}

/** Cheap counts shown next to the project navigation links. A failed request leaves a count unknown (null). */
export const useProjectNavStore = defineStore('projectNav', () => {
  const { get, getRaw } = useApi()

  const projectId = ref<number | null>(null)
  const pendingTitleAbstract = ref<number | null>(null)
  const pendingFullText = ref<number | null>(null)
  const conflicts = ref<number | null>(null)
  const criteria = ref<number | null>(null)
  /** True once the last refresh has finished, whether its requests succeeded or failed. */
  const settled = ref(false)

  const reset = () => {
    projectId.value = null
    pendingTitleAbstract.value = null
    pendingFullText.value = null
    conflicts.value = null
    criteria.value = null
    settled.value = false
  }

  const fetchPending = async (id: number, stage: CountedStage): Promise<number | null> => {
    try {
      const res = await getRaw<PaginatedResponse<Article>>(`/projects/${id}/articles`, {
        params: { pending_for_me: true, stage, per_page: 1 },
      })
      return res.meta.pagination.total_items
    } catch {
      return null
    }
  }

  /** Apply a result only if the user has not switched to another project meanwhile. */
  const ifCurrent = (id: number, apply: () => void) => {
    if (projectId.value === id) apply()
  }

  const refreshScreening = async (id: number) => {
    projectId.value = id
    const [ta, ft] = await Promise.all([fetchPending(id, 'title_abstract'), fetchPending(id, 'full_text')])
    ifCurrent(id, () => {
      pendingTitleAbstract.value = ta
      pendingFullText.value = ft
    })
  }

  const refresh = async (id: number, opts: NavRefreshOptions) => {
    if (projectId.value !== id) reset()
    projectId.value = id
    settled.value = false
    const tasks: Promise<void>[] = [
      get<Criterion[]>(`/projects/${id}/criteria`)
        .then((list) => ifCurrent(id, () => (criteria.value = list.filter((c) => c.is_active).length)))
        .catch(() => undefined),
    ]
    if (opts.canReview) tasks.push(refreshScreening(id))
    if (opts.isOwner) {
      tasks.push(
        get<Conflict[]>(`/projects/${id}/screening/conflicts`)
          .then((list) => ifCurrent(id, () => (conflicts.value = list.length)))
          .catch(() => undefined)
      )
    }
    await Promise.all(tasks)
    ifCurrent(id, () => (settled.value = true))
  }

  const setConflicts = (n: number) => {
    conflicts.value = n
  }

  return {
    projectId,
    pendingTitleAbstract,
    pendingFullText,
    conflicts,
    criteria,
    settled,
    refresh,
    refreshScreening,
    setConflicts,
    reset,
  }
})
