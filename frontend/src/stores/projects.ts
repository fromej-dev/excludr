import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Project, ProjectCreate, ProjectUpdate } from '@/types'

export const useProjectsStore = defineStore('projects', () => {
  const { get, post, patch, delete: del } = useApi()

  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const fetchProjects = async () => {
    loading.value = true
    error.value = null

    try {
      projects.value = await get<Project[]>('/projects')
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch projects'
    } finally {
      loading.value = false
    }
  }

  const fetchProject = async (id: number) => {
    loading.value = true
    error.value = null

    try {
      currentProject.value = await get<Project>(`/projects/${id}`)
      return currentProject.value
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch project'
      return null
    } finally {
      loading.value = false
    }
  }

  const createProject = async (data: ProjectCreate) => {
    loading.value = true
    error.value = null

    try {
      const newProject = await post<Project>('/projects', data)
      projects.value.unshift(newProject)
      return newProject
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to create project'
      return null
    } finally {
      loading.value = false
    }
  }

  const updateProject = async (id: number, data: ProjectUpdate) => {
    loading.value = true
    error.value = null

    try {
      const updatedProject = await patch<Project>(`/projects/${id}`, data)

      // Update in list
      const index = projects.value.findIndex((p) => p.id === id)
      if (index !== -1) {
        projects.value[index] = updatedProject
      }

      // Update current if it's the same
      if (currentProject.value?.id === id) {
        currentProject.value = updatedProject
      }

      return updatedProject
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to update project'
      return null
    } finally {
      loading.value = false
    }
  }

  const deleteProject = async (id: number) => {
    loading.value = true
    error.value = null

    try {
      await del(`/projects/${id}`)
      projects.value = projects.value.filter((p) => p.id !== id)
      if (currentProject.value?.id === id) {
        currentProject.value = null
      }
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to delete project'
      return false
    } finally {
      loading.value = false
    }
  }

  const uploadFile = async (projectId: number, file: File) => {
    loading.value = true
    error.value = null

    try {
      const formData = new FormData()
      formData.append('file', file)

      // Determine endpoint based on file extension
      const fileExtension = file.name.split('.').pop()?.toLowerCase()
      let endpoint: string

      if (fileExtension === 'csv' || fileExtension === 'txt') {
        endpoint = `/projects/${projectId}/upload/pubmed`
      } else if (fileExtension === 'ris') {
        endpoint = `/projects/${projectId}/upload/ris`
      } else {
        error.value = 'Unsupported file type. Please upload .ris, .txt, or .csv files.'
        return null
      }

      const updatedProject = await post<Project>(endpoint, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      // Update the project in the list
      const index = projects.value.findIndex((p) => p.id === projectId)
      if (index !== -1) {
        projects.value[index] = updatedProject
      }

      if (currentProject.value?.id === projectId) {
        currentProject.value = updatedProject
      }

      return updatedProject
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to upload file'
      return null
    } finally {
      loading.value = false
    }
  }

  // Keep backward compatibility
  const uploadRisFile = uploadFile

  return {
    projects,
    currentProject,
    loading,
    error,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    deleteProject,
    uploadFile,
    uploadRisFile,
  }
})
