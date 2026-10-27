import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { ImportBatch, ImportKind, ImportResult, UploadResponse } from '@/types'

export type UploadState = 'idle' | 'uploading' | 'processing' | 'done' | 'error'

export const useImportsStore = defineStore('imports', () => {
  const { get, post } = useApi()

  const batches = ref<ImportBatch[]>([])
  const state = ref<UploadState>('idle')
  const percent = ref(0)
  const result = ref<ImportResult | null>(null)
  const resultFilename = ref<string | null>(null)
  const error = ref<string | null>(null)

  const fetchBatches = async (projectId: number) => {
    try {
      batches.value = await get<ImportBatch[]>(`/projects/${projectId}/imports`)
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load import history')
    }
  }

  const upload = async (projectId: number, kind: ImportKind, file: File) => {
    state.value = 'uploading'
    percent.value = 0
    result.value = null
    resultFilename.value = file.name
    error.value = null

    const form = new FormData()
    form.append('file', file)
    try {
      const res = await post<UploadResponse>(`/projects/${projectId}/upload/${kind}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 0,
        onUploadProgress: (e) => {
          if (e.total) percent.value = Math.round((e.loaded / e.total) * 100)
          if (e.total && e.loaded >= e.total) state.value = 'processing'
        },
      })
      result.value = res.result
      if (res.result.status === 'Error') {
        state.value = 'error'
        error.value = res.result.message ?? 'Import failed'
        return false
      }
      state.value = 'done'
      await fetchBatches(projectId)
      return true
    } catch (err: unknown) {
      state.value = 'error'
      error.value = getErrorMessage(err, 'Upload failed')
      return false
    }
  }

  const resetUpload = () => {
    state.value = 'idle'
    percent.value = 0
    result.value = null
    error.value = null
  }

  return { batches, state, percent, result, resultFilename, error, fetchBatches, upload, resetUpload }
})
