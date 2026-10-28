import { ref, watch, type Ref } from 'vue'
import { useScreeningStore } from '@/stores/screening'

/** How many queued articles after the current one the AI should have screened in advance. */
export const LOOKAHEAD = 2

const STORAGE_KEY = 'excludr_ai_lookahead'

const readEnabled = (): boolean => {
  try {
    return localStorage.getItem(STORAGE_KEY) !== '0'
  } catch {
    return true
  }
}

/**
 * "Stay two ahead": while a reviewer screens, make sure the AI has screened (or is screening) the
 * article on screen plus the next {@link LOOKAHEAD} articles in their queue, so the AI verdict is
 * ready when they get there, without batch-screening the whole project.
 *
 * - The queue is `fetchQueueIds(projectId, stage)` (ascending ids); "next" = the ids after the
 *   current one, no wrapping.
 * - Each id is sent to `run-ai` at most once per project + stage while the view is open (the server
 *   also skips ids that are already screened or already queued by another batch).
 * - A 400 (no active criteria) or 503 (AI not configured) stops the lookahead for this session and
 *   sets `unavailable` to a short reason; nothing is toasted.
 * - Never blocks the UI: requests run in the background; results arrive over the websocket.
 */
export function useAiLookahead(options: {
  projectId: Ref<number>
  stage: Ref<string>
  currentArticleId: Ref<number | null | undefined>
  /** Reviewer role or higher (only reviewers may run the AI). */
  canRun: Ref<boolean>
}) {
  const screeningStore = useScreeningStore()

  const enabled = ref(readEnabled())
  const unavailable = ref<string | null>(null)
  // Ids already sent to run-ai, per `${projectId}:${stage}`
  const requested = new Map<string, Set<number>>()

  watch(enabled, (on) => {
    try {
      localStorage.setItem(STORAGE_KEY, on ? '1' : '0')
    } catch {
      /* storage unavailable */
    }
  })

  const requestedFor = (key: string) => {
    let set = requested.get(key)
    if (!set) {
      set = new Set()
      requested.set(key, set)
    }
    return set
  }

  const ensure = async () => {
    const projectId = options.projectId.value
    const stage = options.stage.value
    const current = options.currentArticleId.value
    if (!enabled.value || unavailable.value || !options.canRun.value || !current) return
    if (!Number.isFinite(projectId)) return

    const queue = await screeningStore.fetchQueueIds(projectId, stage as 'title_abstract' | 'full_text')
    // The user may have moved on (or switched the lookahead off) while the queue loaded
    if (
      !enabled.value ||
      unavailable.value ||
      options.currentArticleId.value !== current ||
      options.projectId.value !== projectId ||
      options.stage.value !== stage
    ) {
      return
    }
    const ahead = queue.filter((id) => id > current).slice(0, LOOKAHEAD)
    const sent = requestedFor(`${projectId}:${stage}`)
    const wanted = [current, ...ahead].filter((id) => !sent.has(id))
    if (wanted.length === 0) return

    for (const id of wanted) sent.add(id)
    const result = await screeningStore.queueAiScreening(projectId, wanted)
    if (result.status === 'unavailable') {
      unavailable.value = result.reason
    } else if (result.status === 'error') {
      // Transient failure: allow these ids to be asked for again on the next article
      for (const id of wanted) sent.delete(id)
    }
  }

  watch(
    [options.currentArticleId, enabled, options.canRun, options.stage],
    () => {
      void ensure()
    },
    { immediate: true }
  )

  return { enabled, unavailable }
}
