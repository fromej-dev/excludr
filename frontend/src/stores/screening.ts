import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type {
  Article,
  ScreeningDecision,
  ScreeningDecisionCreate,
  ScreeningStage,
  NextArticleResponse,
  PaginatedResponse,
  RunAiResponse,
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
  /** Articles queued for AI screening by the lookahead (`run-ai` with `article_ids`), not yet done. */
  const aiQueuedIds = ref<Set<number>>(new Set())
  // Articles the batch reported on while their run-ai request was still in flight
  const aiSettledIds = new Set<number>()
  // Stage the screening view asked the AI verdict for; websocket refreshes keep to it
  let aiStage: ScreeningStage | undefined
  const currentAiQueued = computed(
    () => currentArticle.value !== null && aiQueuedIds.value.has(currentArticle.value.id)
  )

  const settleAiQueued = (ids: number[]) => {
    const next = new Set(aiQueuedIds.value)
    for (const id of ids) {
      next.delete(id)
      aiSettledIds.add(id)
    }
    aiQueuedIds.value = next
  }

  // WebSocket integration
  let wsUnsubscribe: (() => void) | null = null

  const setupWebSocketListeners = () => {
    const wsStore = useWebSocketStore()

    // Stats are kept live by ProjectView (see useProjectLiveUpdates); here only the open article matters
    wsUnsubscribe = wsStore.onMessage('*', async (response: WebSocketResponse) => {
      const data = response.data
      if (!data || typeof data.project_id !== 'number') return
      const isCurrent =
        data.project_id === currentArticle.value?.project_id && data.article_id === currentArticle.value?.id
      if (
        data.type === 'ai_screening_progress' ||
        data.type === 'ai_screening_error' ||
        data.type === 'ai_screening_skipped'
      ) {
        if (typeof data.article_id === 'number') settleAiQueued([data.article_id])
        // The AI batch just screened the article on screen: show its verdict
        if (data.type === 'ai_screening_progress' && isCurrent) {
          await fetchAiDecision(data.project_id, data.article_id as number, aiStage)
        }
      } else if (data.type === 'ai_screening_complete' && Array.isArray(data.article_ids)) {
        // Safety net: whatever a finished lookahead batch did not report on is no longer queued
        settleAiQueued(data.article_ids.filter((id): id is number => typeof id === 'number'))
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

  /**
   * Queue AI screening of specific articles in the background (the screening lookahead).
   * The server skips articles that are not eligible, already screened, or already queued.
   * Never throws: 400/503 come back as `unavailable` so the caller can stop asking.
   */
  const queueAiScreening = async (
    projectId: number,
    articleIds: number[]
  ): Promise<
    { status: 'queued'; ids: number[] } | { status: 'unavailable'; reason: string } | { status: 'error' }
  > => {
    for (const id of articleIds) aiSettledIds.delete(id)
    try {
      const res = await post<RunAiResponse>(`/projects/${projectId}/screening/run-ai`, {
        article_ids: articleIds,
      })
      const queued = (res.article_ids ?? []).filter((id) => !aiSettledIds.has(id))
      if (queued.length) aiQueuedIds.value = new Set([...aiQueuedIds.value, ...queued])
      return { status: 'queued', ids: queued }
    } catch (err: unknown) {
      const status = getErrorStatus(err)
      if (status === 503) return { status: 'unavailable', reason: 'no AI provider is configured' }
      if (status === 400) return { status: 'unavailable', reason: 'add active criteria first' }
      if (status === 403) return { status: 'unavailable', reason: 'reviewer role required' }
      if (status === 402) return { status: 'unavailable', reason: "this review's plan covers no more AI screening" }
      return { status: 'error' }
    }
  }

  /**
   * Load the latest AI decision for an article. With `stage`, only a decision made at that stage
   * counts (a title/abstract verdict must not pass for the AI's view of the full text).
   */
  const fetchAiDecision = async (projectId: number, articleId: number, stage?: ScreeningStage) => {
    aiStage = stage
    aiScreeningLoading.value = true
    error.value = null

    try {
      const decision = await get<ScreeningDecision>(
        `/projects/${projectId}/screening/articles/${articleId}/ai-decision`,
        stage ? { params: { stage } } : undefined
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
    aiQueuedIds,
    currentAiQueued,
    queueAiScreening,
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
