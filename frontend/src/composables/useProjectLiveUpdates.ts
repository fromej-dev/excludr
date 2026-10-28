import { onUnmounted, watch, type Ref } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'
import { throttle, type Throttled } from '@/utils/throttle'
import type { WebSocketResponse } from '@/types'

/** Per-article events of the bulk jobs (full-text retrieval, AI batch screening). */
const PROGRESS_EVENTS = new Set(['fulltext_progress', 'ai_screening_progress', 'ai_screening_error'])
/** Final event of each bulk job. */
const COMPLETE_EVENTS = new Set(['fulltext_complete', 'ai_screening_complete'])

export const LIVE_REFRESH_MS = 1500

/** True when a websocket message belongs to project `id`. */
export function isForProject(msg: WebSocketResponse, id: number): boolean {
  const pid = msg.data?.project_id
  // Batch events carry project_id; without it only trust the project room itself
  if (typeof pid === 'number') return pid === id
  return msg.room === `project_${id}`
}

/**
 * While the user is inside a project, stay in its websocket room and call `refresh(projectId)` when a
 * bulk job makes progress: throttled to once per `intervalMs` (the trailing call always runs, so the
 * final numbers land) and once more, immediately, when the job completes. Events of other projects
 * are ignored; the room and listener are dropped when the project changes or the view unmounts.
 */
export function useProjectLiveUpdates(
  projectId: Ref<number>,
  refresh: (id: number) => void,
  intervalMs = LIVE_REFRESH_MS
) {
  const wsStore = useWebSocketStore()
  let detach: (() => void) | null = null

  const attach = (id: number) => {
    const throttled: Throttled = throttle(() => refresh(id), intervalMs)
    wsStore.joinProjectRoom(id)
    const off = wsStore.onMessage('*', (msg: WebSocketResponse) => {
      const kind = msg.data?.type
      if (typeof kind !== 'string' || !isForProject(msg, id)) return
      if (COMPLETE_EVENTS.has(kind)) throttled.flush()
      else if (PROGRESS_EVENTS.has(kind)) throttled.call()
    })
    detach = () => {
      off()
      throttled.cancel()
      wsStore.leaveProjectRoom(id)
      detach = null
    }
  }

  watch(
    projectId,
    (id) => {
      detach?.()
      if (Number.isFinite(id)) attach(id)
    },
    { immediate: true }
  )
  onUnmounted(() => detach?.())
}
