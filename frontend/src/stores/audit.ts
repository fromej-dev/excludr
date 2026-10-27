import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { AuditEvent, PaginatedResponse } from '@/types'

export const useAuditStore = defineStore('audit', () => {
  const { getRaw } = useApi()

  const events = ref<AuditEvent[]>([])
  const page = ref(1)
  const perPage = ref(20)
  const totalPages = ref(0)
  const totalItems = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchEvents = async (projectId: number, targetPage = 1) => {
    loading.value = true
    error.value = null
    try {
      const res = await getRaw<PaginatedResponse<AuditEvent>>(`/projects/${projectId}/audit`, {
        params: { page: targetPage, per_page: perPage.value },
      })
      events.value = res.data
      page.value = res.meta.pagination.current_page
      totalPages.value = res.meta.pagination.total_pages
      totalItems.value = res.meta.pagination.total_items
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load audit log')
    } finally {
      loading.value = false
    }
  }

  return { events, page, perPage, totalPages, totalItems, loading, error, fetchEvents }
})
