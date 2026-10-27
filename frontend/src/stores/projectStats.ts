import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { ScreeningStats } from '@/types'
import { getErrorMessage } from '@/utils/errors'

/**
 * Screening statistics of the open project, shared by the Overview progress, the next-step card and
 * the screening toolbar. ProjectView loads it and keeps it live while bulk jobs run.
 */
export const useProjectStatsStore = defineStore('projectStats', () => {
  const { get } = useApi()

  const projectId = ref<number | null>(null)
  const stats = ref<ScreeningStats | null>(null)
  const error = ref<string | null>(null)
  /** True once a request for the current project has finished, successfully or not. */
  const settled = ref(false)

  // Requests are numbered so a slow, older response never overwrites a newer one
  let seq = 0
  let applied = 0
  /** Requests numbered at or below this were issued before the last clear and are ignored. */
  let floor = 0

  const reset = () => {
    floor = seq
    projectId.value = null
    stats.value = null
    error.value = null
    settled.value = false
  }

  /**
   * Fetch the stats of project `id`. Switching project clears the old numbers first; a failed refresh
   * keeps the last good numbers (stats stay null only if nothing has loaded yet).
   */
  const fetch = async (id: number, opts: { clear?: boolean } = {}) => {
    if (projectId.value !== id || opts.clear) {
      reset()
      projectId.value = id
    }
    const mine = ++seq
    const live = () => projectId.value === id && mine > floor
    const current = () => live() && mine > applied
    try {
      const result = await get<ScreeningStats>(`/projects/${id}/screening/stats`)
      if (current()) {
        applied = mine
        stats.value = result
        error.value = null
      }
    } catch (err: unknown) {
      if (current()) {
        applied = mine
        error.value = getErrorMessage(err, 'Failed to fetch screening stats')
      }
    } finally {
      if (live()) settled.value = true
    }
  }

  return { projectId, stats, error, settled, fetch, reset }
})
