import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { useWebSocketStore } from './websocket'
import { getErrorMessage } from '@/utils/errors'
import type { RunAiResponse, StaleAiResponse, WebSocketResponse } from '@/types'

/** Live state of a background AI screening batch, fed by the project websocket room. */
export const useAiBatchStore = defineStore('aiBatch', () => {
  const { get, post } = useApi()
  const wsStore = useWebSocketStore()

  const projectId = ref<number | null>(null)
  const running = ref(false)
  const starting = ref(false)
  const screened = ref(0)
  const errors = ref(0)
  const skipped = ref(0) // refused by the plan's AI allowance
  const total = ref(0)
  const staleCount = ref(0)
  const error = ref<string | null>(null)
  const completedAt = ref<number | null>(null)

  const done = computed(() => screened.value + errors.value + skipped.value)
  const percent = computed(() => (total.value ? Math.round((done.value / total.value) * 100) : 0))

  let unsubscribe: (() => void) | null = null
  let onFinished: (() => void) | null = null

  const num = (v: unknown): number => (typeof v === 'number' ? v : 0)

  const handle = (msg: WebSocketResponse) => {
    const data = msg.data
    if (!data || projectId.value === null) return
    // Progress goes to the project room; ignore other rooms' messages
    if (msg.room && msg.room !== `project_${projectId.value}` && !msg.room.startsWith('user_')) return
    // Batch events name their project; the copy sent to the user's own room may be another project's
    if (typeof data.project_id === 'number' && data.project_id !== projectId.value) return
    // Small lookahead batches of the screening view are not "the" project batch
    if (data.targeted === true) return
    const kind = data.type
    if (
      kind === 'ai_screening_progress' ||
      kind === 'ai_screening_error' ||
      kind === 'ai_screening_skipped'
    ) {
      running.value = true
      screened.value = num(data.screened)
      errors.value = num(data.errors)
      skipped.value = num(data.skipped)
      total.value = num(data.total)
    } else if (kind === 'ai_screening_complete') {
      screened.value = num(data.screened)
      errors.value = num(data.errors)
      skipped.value = num(data.skipped)
      total.value = num(data.total)
      running.value = false
      completedAt.value = Date.now()
      void fetchStale(projectId.value)
      onFinished?.()
    }
  }

  /** Join the project room and start listening for batch progress. */
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

  const fetchStale = async (id: number) => {
    try {
      const res = await get<StaleAiResponse>(`/projects/${id}/screening/stale-ai-decisions`)
      staleCount.value = res.count
    } catch {
      staleCount.value = 0
    }
  }

  const start = async (id: number, rescreenStale: boolean) => {
    starting.value = true
    error.value = null
    try {
      const res = await post<RunAiResponse>(`/projects/${id}/screening/run-ai`, undefined, {
        params: { rescreen_stale: rescreenStale },
      })
      if (res.article_count > 0) {
        running.value = true
        screened.value = 0
        errors.value = 0
        skipped.value = 0
        total.value = res.article_count
      }
      return res
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to start AI screening')
      return null
    } finally {
      starting.value = false
    }
  }

  return {
    running,
    starting,
    screened,
    errors,
    skipped,
    total,
    staleCount,
    error,
    completedAt,
    percent,
    done,
    subscribe,
    unsubscribe: unsubscribeAll,
    fetchStale,
    start,
  }
})
