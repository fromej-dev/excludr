import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type {
  Article,
  ArticleStats,
  PaginatedResponse,
  ArticleListOptions,
  RetrieveFullTextBulkResponse,
  WebSocketResponse,
} from '@/types'
import { useWebSocketStore } from './websocket'

export const useArticlesStore = defineStore('articles', () => {
  const { get, getRaw, post } = useApi()

  const articles = ref<Article[]>([])
  const currentArticle = ref<Article | null>(null)
  const stats = ref<ArticleStats | null>(null)
  const pagination = ref({
    total: 0,
    page: 1,
    per_page: 20,
    pages: 0,
  })
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastFetchOptions = ref<{ projectId: number; options?: ArticleListOptions } | null>(null)
  /** Guards against out-of-order responses when filters change quickly. */
  let requestSeq = 0

  // WebSocket integration
  let wsUnsubscribe: (() => void) | null = null

  const setupWebSocketListeners = () => {
    const wsStore = useWebSocketStore()

    wsUnsubscribe = wsStore.onMessage('*', async (response: WebSocketResponse) => {
      // Handle article status updates
      if (response.data?.event === 'article_updated' && response.data?.project_id) {
        await fetchStats(response.data.project_id)

        // Refresh articles list if we have a current project context
        if (lastFetchOptions.value?.projectId === response.data.project_id) {
          await fetchArticles(response.data.project_id, lastFetchOptions.value.options)
        }
      }

      // A full-text batch finished: statuses and sources changed
      if (response.data?.type === 'fulltext_complete' && lastFetchOptions.value) {
        await fetchArticles(lastFetchOptions.value.projectId, lastFetchOptions.value.options)
      }

      // Handle upload completion - refresh stats and articles
      if (response.data?.event === 'upload_complete' && response.data?.project_id) {
        await fetchStats(response.data.project_id)

        if (lastFetchOptions.value?.projectId === response.data.project_id) {
          await fetchArticles(response.data.project_id, lastFetchOptions.value.options)
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

  /**
   * Fetch one page of articles. Search, decision and sort use the `fastapi_fsp`
   * query params (`search`/`search_fields`, `field`/`operator`/`value`, `sort_by`/`order`);
   * `status` and `has_full_text` are explicit endpoint params.
   */
  const fetchArticles = async (projectId: number, options?: ArticleListOptions) => {
    const seq = ++requestSeq
    loading.value = true
    error.value = null

    // Save fetch options for WebSocket refresh
    lastFetchOptions.value = { projectId, options }

    try {
      const params = new URLSearchParams()
      if (options?.status) params.append('status', options.status)
      if (options?.has_full_text !== undefined) {
        params.append('has_full_text', String(options.has_full_text))
      }
      if (options?.final_decision) {
        params.append('field', 'final_decision')
        params.append('operator', 'eq')
        params.append('value', options.final_decision)
      }
      const search = options?.search?.trim()
      if (search) {
        params.append('search', search)
        params.append('search_fields', 'title,authors,journal')
      }
      if (options?.sort_by) {
        params.append('sort_by', options.sort_by)
        params.append('order', options.order ?? 'asc')
      }
      if (options?.page) params.append('page', options.page.toString())
      if (options?.per_page) params.append('per_page', options.per_page.toString())

      const queryString = params.toString()
      const url = `/projects/${projectId}/articles${queryString ? `?${queryString}` : ''}`

      const response = await getRaw<PaginatedResponse<Article>>(url)
      if (seq !== requestSeq) return
      articles.value = response.data
      pagination.value = {
        total: response.meta.pagination.total_items,
        page: response.meta.pagination.current_page,
        per_page: response.meta.pagination.per_page,
        pages: response.meta.pagination.total_pages,
      }
    } catch (err: any) {
      if (seq !== requestSeq) return
      error.value = err.response?.data?.detail || 'Failed to fetch articles'
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  /** Owner only: start full-text retrieval for the given articles (eligible ones are processed). */
  const retrieveFulltext = async (projectId: number, articleIds: number[]) => {
    try {
      return await post<RetrieveFullTextBulkResponse>(
        `/projects/${projectId}/articles/retrieve-fulltext`,
        { article_ids: articleIds },
      )
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to start full-text retrieval'
      return null
    }
  }

  const fetchArticle = async (projectId: number, articleId: number) => {
    loading.value = true
    error.value = null

    try {
      currentArticle.value = await get<Article>(`/projects/${projectId}/articles/${articleId}`)
      return currentArticle.value
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch article'
      return null
    } finally {
      loading.value = false
    }
  }

  const fetchStats = async (projectId: number) => {
    loading.value = true
    error.value = null

    try {
      stats.value = await get<ArticleStats>(`/projects/${projectId}/articles/stats`)
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch stats'
    } finally {
      loading.value = false
    }
  }

  // Initialize WebSocket listeners
  setupWebSocketListeners()

  return {
    articles,
    currentArticle,
    stats,
    pagination,
    loading,
    error,
    fetchArticles,
    retrieveFulltext,
    fetchArticle,
    fetchStats,
    setupWebSocketListeners,
    cleanupWebSocketListeners,
  }
})
