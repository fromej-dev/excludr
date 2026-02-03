import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type {
  Article,
  ScreeningDecision,
  ScreeningDecisionCreate,
  ScreeningStats,
  ScreeningStage,
  WebSocketResponse,
} from '@/types'
import { useWebSocketStore } from './websocket'

export const useScreeningStore = defineStore('screening', () => {
  const { get, post } = useApi()

  const currentArticle = ref<Article | null>(null)
  const decisions = ref<ScreeningDecision[]>([])
  const stats = ref<ScreeningStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const aiDecision = ref<ScreeningDecision | null>(null)
  const aiScreeningLoading = ref(false)

  // WebSocket integration
  let wsUnsubscribe: (() => void) | null = null

  const setupWebSocketListeners = () => {
    const wsStore = useWebSocketStore()

    wsUnsubscribe = wsStore.onMessage('*', async (response: WebSocketResponse) => {
      // Handle screening decision updates
      if (response.data?.event === 'screening_decision' && response.data?.project_id) {
        await fetchStats(response.data.project_id)
      }

      // Handle AI screening completion
      if (response.data?.event === 'ai_screening_complete' && response.data?.project_id) {
        await fetchStats(response.data.project_id)

        // If the completed article is the current one, refresh AI decision
        if (response.data?.article_id && currentArticle.value?.id === response.data.article_id) {
          await fetchAiDecision(response.data.project_id, response.data.article_id)
        }
      }
    })
  }

  const cleanupWebSocketListeners = () => {
    if (wsUnsubscribe) {
      wsUnsubscribe()
      wsUnsubscribe = null
    }
  }

  const fetchNextArticle = async (projectId: number, stage: ScreeningStage) => {
    loading.value = true
    error.value = null

    try {
      currentArticle.value = await get<Article>(
        `/projects/${projectId}/screening/next?stage=${stage}`
      )
      return currentArticle.value
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'No more articles to screen'
      currentArticle.value = null
      return null
    } finally {
      loading.value = false
    }
  }

  const submitDecision = async (
    projectId: number,
    articleId: number,
    decision: ScreeningDecisionCreate
  ) => {
    loading.value = true
    error.value = null

    try {
      const newDecision = await post<ScreeningDecision>(
        `/projects/${projectId}/articles/${articleId}/decisions`,
        decision
      )
      decisions.value.push(newDecision)
      return newDecision
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to submit decision'
      return null
    } finally {
      loading.value = false
    }
  }

  const fetchDecisions = async (projectId: number, articleId: number) => {
    loading.value = true
    error.value = null

    try {
      decisions.value = await get<ScreeningDecision[]>(
        `/projects/${projectId}/articles/${articleId}/decisions`
      )
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch decisions'
    } finally {
      loading.value = false
    }
  }

  const fetchStats = async (projectId: number) => {
    loading.value = true
    error.value = null

    try {
      stats.value = await get<ScreeningStats>(`/projects/${projectId}/screening/stats`)
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch screening stats'
    } finally {
      loading.value = false
    }
  }

  const triggerAiScreening = async (projectId: number, articleId: number) => {
    aiScreeningLoading.value = true
    error.value = null

    try {
      const decision = await post<ScreeningDecision>(
        `/projects/${projectId}/screening/articles/${articleId}/screen-ai`
      )
      aiDecision.value = decision
      return decision
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to trigger AI screening'
      return null
    } finally {
      aiScreeningLoading.value = false
    }
  }

  const triggerBatchAiScreening = async (projectId: number) => {
    aiScreeningLoading.value = true
    error.value = null

    try {
      const result = await post<{ message: string; article_count: number }>(
        `/projects/${projectId}/screening/run-ai`
      )
      return result
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to trigger batch AI screening'
      return null
    } finally {
      aiScreeningLoading.value = false
    }
  }

  const fetchAiDecision = async (projectId: number, articleId: number) => {
    aiScreeningLoading.value = true
    error.value = null

    try {
      const decision = await get<ScreeningDecision>(
        `/projects/${projectId}/screening/articles/${articleId}/ai-decision`
      )
      aiDecision.value = decision
      return decision
    } catch (err: any) {
      // 404 is expected when no AI decision exists
      if (err.response?.status === 404) {
        aiDecision.value = null
      } else {
        error.value = err.response?.data?.detail || 'Failed to fetch AI decision'
      }
      return null
    } finally {
      aiScreeningLoading.value = false
    }
  }

  // Initialize WebSocket listeners
  setupWebSocketListeners()

  return {
    currentArticle,
    decisions,
    stats,
    loading,
    error,
    aiDecision,
    aiScreeningLoading,
    fetchNextArticle,
    submitDecision,
    fetchDecisions,
    fetchStats,
    triggerAiScreening,
    triggerBatchAiScreening,
    fetchAiDecision,
    setupWebSocketListeners,
    cleanupWebSocketListeners,
  }
})
