import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Criterion, CriterionCreate, CriterionUpdate, CriteriaReorder } from '@/types'

export const useCriteriaStore = defineStore('criteria', () => {
  const { get, post, patch, delete: del } = useApi()

  const criteria = ref<Criterion[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const inclusionCriteria = computed(() =>
    criteria.value.filter((c) => c.type === 'inclusion').sort((a, b) => a.order - b.order)
  )

  const exclusionCriteria = computed(() =>
    criteria.value.filter((c) => c.type === 'exclusion').sort((a, b) => a.order - b.order)
  )

  const fetchCriteria = async (projectId: number) => {
    loading.value = true
    error.value = null

    try {
      criteria.value = await get<Criterion[]>(`/projects/${projectId}/criteria`)
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch criteria'
    } finally {
      loading.value = false
    }
  }

  const createCriterion = async (projectId: number, data: CriterionCreate) => {
    loading.value = true
    error.value = null

    try {
      const newCriterion = await post<Criterion>(`/projects/${projectId}/criteria`, data)
      criteria.value.push(newCriterion)
      return newCriterion
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to create criterion'
      return null
    } finally {
      loading.value = false
    }
  }

  const updateCriterion = async (
    projectId: number,
    criterionId: number,
    data: CriterionUpdate
  ) => {
    loading.value = true
    error.value = null

    try {
      const updatedCriterion = await patch<Criterion>(
        `/projects/${projectId}/criteria/${criterionId}`,
        data
      )

      const index = criteria.value.findIndex((c) => c.id === criterionId)
      if (index !== -1) {
        criteria.value[index] = updatedCriterion
      }

      return updatedCriterion
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to update criterion'
      return null
    } finally {
      loading.value = false
    }
  }

  const deleteCriterion = async (projectId: number, criterionId: number) => {
    loading.value = true
    error.value = null

    try {
      await del(`/projects/${projectId}/criteria/${criterionId}`)
      criteria.value = criteria.value.filter((c) => c.id !== criterionId)
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to delete criterion'
      return false
    } finally {
      loading.value = false
    }
  }

  const reorderCriteria = async (projectId: number, criterionIds: number[]) => {
    loading.value = true
    error.value = null

    try {
      const reorderedCriteria = await post<Criterion[]>(
        `/projects/${projectId}/criteria/reorder`,
        { criterion_ids: criterionIds }
      )
      criteria.value = reorderedCriteria
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to reorder criteria'
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    criteria,
    inclusionCriteria,
    exclusionCriteria,
    loading,
    error,
    fetchCriteria,
    createCriterion,
    updateCriterion,
    deleteCriterion,
    reorderCriteria,
  }
})
