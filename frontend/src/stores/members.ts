import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { useAuthStore } from './auth'
import { useProjectsStore } from './projects'
import { getErrorMessage } from '@/utils/errors'
import type { ProjectMember, ProjectRole } from '@/types'

const ROLE_RANK: Record<ProjectRole, number> = { viewer: 1, reviewer: 2, owner: 3 }

/** Members of the current project and the current user's role in it. */
export const useMembersStore = defineStore('members', () => {
  const { get, post, patch, delete: del } = useApi()
  const authStore = useAuthStore()
  const projectsStore = useProjectsStore()

  const members = ref<ProjectMember[]>([])
  const loadedProjectId = ref<number | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** Role of the signed-in user; null while unknown or when not a member. */
  const role = computed<ProjectRole | null>(() => {
    const userId = authStore.user?.id
    if (userId === undefined) return null
    const project = projectsStore.currentProject
    // Project.owner_id is authoritative for ownership
    if (project && loadedProjectId.value === project.id && project.owner_id === userId) return 'owner'
    return members.value.find((m) => m.user_id === userId)?.role ?? null
  })

  const hasRole = (min: ProjectRole): boolean =>
    role.value !== null && ROLE_RANK[role.value] >= ROLE_RANK[min]

  const isOwner = computed(() => hasRole('owner'))
  const canReview = computed(() => hasRole('reviewer'))

  const fetchMembers = async (projectId: number) => {
    loading.value = true
    error.value = null
    if (loadedProjectId.value !== projectId) members.value = []
    try {
      members.value = await get<ProjectMember[]>(`/projects/${projectId}/members`)
      loadedProjectId.value = projectId
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load members')
    } finally {
      loading.value = false
    }
  }

  const addMember = async (projectId: number, email: string, memberRole: ProjectRole) => {
    error.value = null
    try {
      const member = await post<ProjectMember>(`/projects/${projectId}/members`, {
        email,
        role: memberRole,
      })
      members.value.push(member)
      return true
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to add member')
      return false
    }
  }

  const changeRole = async (projectId: number, userId: number, memberRole: ProjectRole) => {
    error.value = null
    try {
      const updated = await patch<ProjectMember>(`/projects/${projectId}/members/${userId}`, {
        role: memberRole,
      })
      const idx = members.value.findIndex((m) => m.user_id === userId)
      if (idx !== -1) members.value[idx] = updated
      return true
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to change role')
      return false
    }
  }

  const removeMember = async (projectId: number, userId: number) => {
    error.value = null
    try {
      await del(`/projects/${projectId}/members/${userId}`)
      members.value = members.value.filter((m) => m.user_id !== userId)
      return true
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to remove member')
      return false
    }
  }

  const reset = () => {
    members.value = []
    loadedProjectId.value = null
    error.value = null
  }

  return {
    members,
    loading,
    error,
    role,
    isOwner,
    canReview,
    hasRole,
    fetchMembers,
    addMember,
    changeRole,
    removeMember,
    reset,
  }
})
