import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Article, ArticleStats, PaginatedResponse, ArticleStatus, FinalDecision } from '@/types'

export const useArticlesStore = defineStore('articles', () => {
  const { get, getRaw } = useApi()

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

  const fetchArticles = async (
    projectId: number,
    options?: {
      status?: ArticleStatus
      final_decision?: FinalDecision
      page?: number
      per_page?: number
    }
  ) => {
    loading.value = true
    error.value = null

    try {
      const params = new URLSearchParams()
      if (options?.status) params.append('status', options.status)
      if (options?.final_decision) params.append('final_decision', options.final_decision)
      if (options?.page) params.append('page', options.page.toString())
      if (options?.per_page) params.append('per_page', options.per_page.toString())

      const queryString = params.toString()
      const url = `/projects/${projectId}/articles${queryString ? `?${queryString}` : ''}`

      const response = await getRaw<PaginatedResponse<Article>>(url)
      articles.value = response.data
      pagination.value = {
        total: response.meta.pagination.total_items,
        page: response.meta.pagination.current_page,
        per_page: response.meta.pagination.per_page,
        pages: response.meta.pagination.total_pages,
      }
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch articles'
    } finally {
      loading.value = false
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

  return {
    articles,
    currentArticle,
    stats,
    pagination,
    loading,
    error,
    fetchArticles,
    fetchArticle,
    fetchStats,
  }
})
