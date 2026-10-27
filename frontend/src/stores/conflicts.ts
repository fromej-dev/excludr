import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { Conflict, ResolveRequest, ScreeningDecision } from '@/types'

export const useConflictsStore = defineStore('conflicts', () => {
  const { get, post } = useApi()

  const conflicts = ref<Conflict[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchConflicts = async (projectId: number) => {
    loading.value = true
    error.value = null
    try {
      conflicts.value = await get<Conflict[]>(`/projects/${projectId}/screening/conflicts`)
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load conflicts')
    } finally {
      loading.value = false
    }
  }

  const resolve = async (projectId: number, articleId: number, body: ResolveRequest) => {
    try {
      await post<ScreeningDecision>(
        `/projects/${projectId}/screening/articles/${articleId}/resolve`,
        body
      )
      conflicts.value = conflicts.value.filter((c) => c.article_id !== articleId)
      return null
    } catch (err: unknown) {
      return getErrorMessage(err, 'Failed to resolve conflict')
    }
  }

  return { conflicts, loading, error, fetchConflicts, resolve }
})
