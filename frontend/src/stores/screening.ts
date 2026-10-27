import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type {
  Article,
  ScreeningDecision,
  ScreeningDecisionCreate,
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
  const loading = ref(false)
  const error = ref<string | null>(null)
  const aiDecision = ref<ScreeningDecision | null>(null)
  const aiScreeningLoading = ref(false)

  // WebSocket integration
  let wsUnsubscribe: (() => void) | null = null

  const setupWebSocketListeners = () => {
    const wsStore = useWebSocketStore()

    // Stats are kept live by ProjectView (see useProjectLiveUpdates); here only the open article matters
    wsUnsubscribe = wsStore.onMessage('*', async (response: WebSocketResponse) => {
      const data = response.data
      // The AI batch just screened the article on screen: show its verdict
      if (
        data?.type === 'ai_screening_progress' &&
        typeof data.project_id === 'number' &&
        data.project_id === currentArticle.value?.project_id &&
        data.article_id === currentArticle.value?.id
      ) {
        await fetchAiDecision(data.project_id, data.article_id)
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

  /** Ids of articles at `stage` this reviewer still has to decide, ascending. */
  const fetchQueueIds = async (projectId: number, stage: ScreeningStage) => {
    try {
      const res = await getRaw<PaginatedResponse<Article>>(`/projects/${projectId}/articles`, {
        params: { pending_for_me: true, stage, per_page: 100 },
      })
      return res.data.map((a) => a.id).sort((x, y) => x - y)
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
    loading,
    error,
    aiDecision,
    aiScreeningLoading,
    fetchNextArticle,
    submitDecision,
    fetchDecisions,
    triggerAiScreening,
    loadArticle,
    fetchQueueIds,
    fetchAiDecision,
    setupWebSocketListeners,
    cleanupWebSocketListeners,
  }
})
