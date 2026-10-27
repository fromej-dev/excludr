import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type {
  Article,
  ScreeningDecision,
  ScreeningDecisionCreate,
  ScreeningStats,
  ScreeningStage,
  NextArticleResponse,
  PaginatedResponse,
  WebSocketResponse,
} from '@/types'
import { useWebSocketStore } from './websocket'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'

export const useScreeningStore = defineStore('screening', () => {
  const { get, getRaw, post } = useApi()

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
      // The envelope is `{ article: Article | null }`, so read it raw
      const res = await getRaw<NextArticleResponse>(`/projects/${projectId}/screening/next`, {
        params: { stage },
      })
      currentArticle.value = res.article
      return currentArticle.value
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load the next article')
      currentArticle.value = null
      return null
    } finally {
      loading.value = false
    }
  }

  /** Load a specific article into the screening view (used for previous/next navigation). */
  const loadArticle = async (projectId: number, articleId: number) => {
    loading.value = true
    error.value = null
    try {
      currentArticle.value = await get<Article>(`/projects/${projectId}/articles/${articleId}`)
      return currentArticle.value
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load article')
      return null
    } finally {
      loading.value = false
    }
  }

  /** Ids of articles in the given stage still in the screening pipeline, ascending. */
  const fetchQueueIds = async (projectId: number, stage: ScreeningStage) => {
    try {
      const res = await getRaw<PaginatedResponse<Article>>(`/projects/${projectId}/articles`, {
        params: { stage, per_page: 100 },
      })
      return res.data
        .filter((a) => a.status === 'screening' || a.status === 'full_text_retrieved')
        .map((a) => a.id)
        .sort((x, y) => x - y)
    } catch {
      return []
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
        `/projects/${projectId}/screening/articles/${articleId}/decisions`,
        decision
      )
      decisions.value.push(newDecision)
      return newDecision
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to submit decision')
      return null
    } finally {
      loading.value = false
    }
  }

  const fetchDecisions = async (projectId: number, articleId: number) => {
    loading.value = true
    error.value = null

    try {
      // Paginated envelope; the backend hides other reviewers' decisions when blinded
      const res = await getRaw<PaginatedResponse<ScreeningDecision>>(
        `/projects/${projectId}/screening/articles/${articleId}/decisions`,
        { params: { per_page: 100 } }
      )
      decisions.value = res.data
      return res.data
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to fetch decisions')
      decisions.value = []
      return []
    } finally {
      loading.value = false
    }
  }

  const fetchStats = async (projectId: number) => {
    loading.value = true
    error.value = null

    try {
      stats.value = await get<ScreeningStats>(`/projects/${projectId}/screening/stats`)
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to fetch screening stats')
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
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to trigger AI screening')
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
    } catch (err: unknown) {
      // 404 is expected when no AI decision exists
      if (getErrorStatus(err) === 404) {
        aiDecision.value = null
      } else {
        error.value = getErrorMessage(err, 'Failed to fetch AI decision')
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
    loadArticle,
    fetchQueueIds,
    fetchAiDecision,
    setupWebSocketListeners,
    cleanupWebSocketListeners,
  }
})
