import { defineStore } from 'pinia'
import { useApi } from '@/composables/useApi'
import type {
  AdminOverview,
  AdminPage,
  AdminPayment,
  AdminProject,
  AdminProjectState,
  AdminUser,
  AdminUserDetail,
  AiUsageFilters,
  AiUsageGroupBy,
  AiUsageReport,
  PaymentStatus,
} from '@/types'
import { filenameFromDisposition } from '@/stores/reports'

export interface ListParams {
  page?: number
  page_size?: number
  search?: string
}

/** Drop empty filters so they are not sent as `?search=`. */
const clean = <T extends object>(params: T) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null))

/** Admin API calls (superusers only). Views keep their own list state. */
export const useAdminStore = defineStore('admin', () => {
  const { get, post, patch, api } = useApi()

  const overview = () => get<AdminOverview>('/admin/overview')

  const users = (params: ListParams) =>
    get<AdminPage<AdminUser>>('/admin/users', { params: clean(params) })

  const user = (id: number) => get<AdminUserDetail>(`/admin/users/${id}`)

  const updateUser = (id: number, changes: { is_active?: boolean; is_superuser?: boolean }) =>
    patch<AdminUserDetail>(`/admin/users/${id}`, changes)

  const projects = (params: ListParams & { state?: AdminProjectState | '' }) =>
    get<AdminPage<AdminProject>>('/admin/projects', { params: clean(params) })

  const grantPass = (
    projectId: number,
    body: { tier: string; fulltext_limit?: number; days: number }
  ) => post(`/admin/projects/${projectId}/plan`, body)

  const updatePass = (
    projectId: number,
    body: { fulltext_limit?: number; expires_at?: string }
  ) => patch(`/admin/projects/${projectId}/plan`, body)

  const payments = (params: ListParams & { status?: PaymentStatus | '' }) =>
    get<AdminPage<AdminPayment>>('/admin/payments', { params: clean(params) })

  const aiUsage = (params: AiUsageFilters & { group_by: AiUsageGroupBy; limit?: number }) =>
    get<AiUsageReport>('/admin/ai-usage', { params: clean(params) })

  /** Download AI usage as CSV: the totals per group, or every run without `group_by`. */
  const exportAiUsage = async (params: AiUsageFilters & { group_by?: AiUsageGroupBy }) => {
    const res = await api.get<Blob>('/admin/ai-usage/export', {
      params: clean(params),
      responseType: 'blob',
    })
    const name = filenameFromDisposition(
      res.headers['content-disposition'] as string | undefined,
      'ai-usage.csv'
    )
    const url = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = url
    link.download = name
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    return name
  }

  return {
    overview,
    users,
    user,
    updateUser,
    projects,
    grantPass,
    updatePass,
    payments,
    aiUsage,
    exportAiUsage,
  }
})
