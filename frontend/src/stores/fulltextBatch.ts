import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { useWebSocketStore } from './websocket'
import { getErrorMessage } from '@/utils/errors'
import type { RetrieveFullTextBulkResponse, WebSocketResponse } from '@/types'

/** Live state of a background full-text retrieval batch, fed by the project websocket room. */
export const useFulltextBatchStore = defineStore('fulltextBatch', () => {
  const { post } = useApi()
  const wsStore = useWebSocketStore()

  const projectId = ref<number | null>(null)
  const running = ref(false)
  const starting = ref(false)
  const retrieved = ref(0)
  const errors = ref(0)
  const total = ref(0)
  const error = ref<string | null>(null)
  const completedAt = ref<number | null>(null)

  const done = computed(() => retrieved.value + errors.value)
  const percent = computed(() => (total.value ? Math.round((done.value / total.value) * 100) : 0))

  let unsubscribe: (() => void) | null = null
  let onFinished: (() => void) | null = null

  const num = (v: unknown): number => (typeof v === 'number' ? v : 0)

  const handle = (msg: WebSocketResponse) => {
    const data = msg.data
    if (!data || projectId.value === null) return
    if (msg.room && msg.room !== `project_${projectId.value}` && !msg.room.startsWith('user_')) return
    if (data.type === 'fulltext_progress') {
      running.value = true
      retrieved.value = num(data.retrieved)
      errors.value = num(data.errors)
      total.value = num(data.total)
    } else if (data.type === 'fulltext_complete') {
      retrieved.value = num(data.retrieved)
      errors.value = num(data.errors)
      total.value = num(data.total)
      running.value = false
      completedAt.value = Date.now()
      onFinished?.()
    }
  }

  const subscribe = (id: number, finished?: () => void) => {
    unsubscribeAll()
    projectId.value = id
    onFinished = finished ?? null
    wsStore.joinProjectRoom(id)
    unsubscribe = wsStore.onMessage('*', handle)
  }

  const unsubscribeAll = () => {
    unsubscribe?.()
    unsubscribe = null
    if (projectId.value !== null) wsStore.leaveProjectRoom(projectId.value)
    onFinished = null
  }

  const start = async (id: number) => {
    starting.value = true
    error.value = null
    try {
      const res = await post<RetrieveFullTextBulkResponse>(`/projects/${id}/articles/retrieve-fulltext`)
      if (res.count > 0) {
        running.value = true
        retrieved.value = 0
        errors.value = 0
        total.value = res.count
      }
      return res
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to start full-text retrieval')
      return null
    } finally {
      starting.value = false
    }
  }

  return {
    running,
    starting,
    retrieved,
    errors,
    total,
    error,
    completedAt,
    percent,
    done,
    subscribe,
    unsubscribe: unsubscribeAll,
    start,
  }
})
