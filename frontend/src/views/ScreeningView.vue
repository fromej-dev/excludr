<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useScreeningStore } from '@/stores/screening'
import { useCriteriaStore } from '@/stores/criteria'
import { useMembersStore } from '@/stores/members'
import { useAuthStore } from '@/stores/auth'
import { useWebSocketStore } from '@/stores/websocket'
import type { ScreeningDecisionType, ScreeningStage } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Label from '@/components/ui/Label.vue'
import ScreeningToolbar from '@/components/screening/ScreeningToolbar.vue'
import AiVerdict from '@/components/screening/AiVerdict.vue'
import CriteriaEvaluationList from '@/components/screening/CriteriaEvaluationList.vue'
import ShortcutLegend from '@/components/screening/ShortcutLegend.vue'
import FullTextPanel from '@/components/articles/FullTextPanel.vue'
import { normalizeEvaluations } from '@/utils/criteriaEvaluations'

const route = useRoute()
const screeningStore = useScreeningStore()
const criteriaStore = useCriteriaStore()
const membersStore = useMembersStore()
const authStore = useAuthStore()
const wsStore = useWebSocketStore()

const projectId = computed(() => Number(route.params.id))
const article = computed(() => screeningStore.currentArticle)
const aiDecision = computed(() => screeningStore.aiDecision)
const aiScreeningLoading = computed(() => screeningStore.aiScreeningLoading)
const canReview = computed(() => membersStore.canReview)
const roleKnown = computed(() => membersStore.role !== null)

const stage = ref<Exclude<ScreeningStage, 'completed'>>('title_abstract')
const reasoning = ref('')
const submitting = ref(false)
const myDecision = ref<ScreeningDecisionType | null>(null)

// Articles visited this session, so P/N can step back and forth
const history = ref<number[]>([])
const pos = ref(-1)

const stats = computed(() => screeningStore.stats)
const evaluations = computed(() => normalizeEvaluations(aiDecision.value?.criteria_evaluations))

const articlePane = ref<HTMLElement | null>(null)

/** The last decision this session, so it can be undone (re-opened for a new decision). */
interface LastDecision {
  articleId: number
  toastId: string
}
const lastDecision = ref<LastDecision | null>(null)

const TITLE_MAX = 60
const truncate = (text: string, max: number) => (text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text)

/** Load the reviewer's own previous decision for the current article (never anyone else's). */
const loadMyDecision = async () => {
  myDecision.value = null
  const a = screeningStore.currentArticle
  const me = authStore.user?.id
  if (!a || me === undefined) return
  const decisions = await screeningStore.fetchDecisions(projectId.value, a.id)
  myDecision.value =
    decisions.find((d) => d.source === 'human' && d.reviewer_id === me && d.stage === stage.value)
      ?.decision ?? null
}

const afterArticleLoaded = async () => {
  reasoning.value = ''
  const a = screeningStore.currentArticle
  if (!a) {
    myDecision.value = null
    return
  }
  await Promise.all([
    screeningStore.fetchAiDecision(projectId.value, a.id),
    loadMyDecision(),
  ])
}

const pushHistory = () => {
  const a = screeningStore.currentArticle
  if (!a) return
  history.value = [...history.value.slice(0, pos.value + 1), a.id]
  pos.value = history.value.length - 1
}

/** Load the next article this reviewer has not decided yet. */
const loadNextUnscreened = async () => {
  await screeningStore.fetchNextArticle(projectId.value, stage.value)
  pushHistory()
  await afterArticleLoaded()
}

const goTo = async (index: number) => {
  pos.value = index
  await screeningStore.loadArticle(projectId.value, history.value[index])
  await afterArticleLoaded()
}

const nextArticle = async () => {
  if (!article.value || submitting.value) return
  if (pos.value < history.value.length - 1) {
    await goTo(pos.value + 1)
    return
  }
  // Skip without deciding: pick another queued article we have not visited
  const queue = await screeningStore.fetchQueueIds(projectId.value, stage.value)
  const seen = new Set(history.value)
  const currentId = article.value.id
  const candidates = queue.filter((id) => !seen.has(id))
  const nextId = candidates.find((id) => id > currentId) ?? candidates[0]
  if (nextId === undefined) {
    wsStore.addNotification('No other articles in the queue', 'info', 2500)
    return
  }
  await screeningStore.loadArticle(projectId.value, nextId)
  pushHistory()
  await afterArticleLoaded()
}

const previousArticle = async () => {
  if (submitting.value || pos.value <= 0) return
  await goTo(pos.value - 1)
}

const submitDecision = async (decision: ScreeningDecisionType) => {
  if (!article.value || submitting.value || !canReview.value) return

  submitting.value = true
  const saved = await screeningStore.submitDecision(projectId.value, article.value.id, {
    stage: stage.value,
    decision,
    source: 'human',
    reasoning: reasoning.value || undefined,
  })
  submitting.value = false

  if (!saved) {
    wsStore.addNotification(screeningStore.error ?? 'Failed to save decision', 'error')
    return
  }
  const decidedId = article.value.id
  const decidedTitle = article.value.title || 'Untitled'
  await screeningStore.fetchStats(projectId.value)
  const toastId = wsStore.addNotification(
    `${decisionPast[decision]}: ${truncate(decidedTitle, TITLE_MAX)}`,
    'success',
    8000,
    { label: 'Undo', onClick: () => void undoDecision(decidedId) }
  )
  lastDecision.value = { articleId: decidedId, toastId }
  if (pos.value < history.value.length - 1) {
    await goTo(pos.value + 1)
  } else {
    await loadNextUnscreened()
  }
}

const decisionPast: Record<ScreeningDecisionType, string> = {
  include: 'Included',
  exclude: 'Excluded',
  uncertain: 'Marked uncertain',
}

/**
 * Decisions are append-only on the backend, so "undo" navigates back to the article so it can
 * be re-decided; the newest human decision replaces the old one.
 */
const undoDecision = async (articleId?: number) => {
  if (submitting.value) return
  const target = articleId ?? lastDecision.value?.articleId
  if (target === undefined) return
  const index = history.value.lastIndexOf(target)
  if (index === -1) {
    wsStore.addNotification('That article is no longer in this session', 'info', 2500)
    return
  }
  if (lastDecision.value?.articleId === target) {
    wsStore.removeNotification(lastDecision.value.toastId)
    lastDecision.value = null
  }
  await goTo(index)
}

const triggerAiScreening = async () => {
  if (!article.value) return
  const result = await screeningStore.triggerAiScreening(projectId.value, article.value.id)
  if (result) {
    wsStore.addNotification('AI screening completed', 'success')
  } else {
    wsStore.addNotification(screeningStore.error ?? 'AI screening failed', 'error')
  }
}

const resetQueue = async () => {
  history.value = []
  pos.value = -1
  if (canReview.value) await loadNextUnscreened()
}

const setStage = async (value: 'title_abstract' | 'full_text') => {
  if (stage.value === value) return
  stage.value = value
  lastDecision.value = null
  await resetQueue()
}

const refreshArticle = () => {
  if (article.value) void screeningStore.loadArticle(projectId.value, article.value.id)
}

const onBatchFinished = async () => {
  await screeningStore.fetchStats(projectId.value)
  if (article.value) await screeningStore.fetchAiDecision(projectId.value, article.value.id)
}

// Keyboard shortcuts; ignored while typing or with modifier keys
const isTypingTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.isContentEditable ||
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  )
}

const onKeydown = (event: KeyboardEvent) => {
  if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return
  if (isTypingTarget(event.target)) return
  switch (event.key.toLowerCase()) {
    case 'i':
      void submitDecision('include')
      break
    case 'e':
      void submitDecision('exclude')
      break
    case 'u':
      void submitDecision('uncertain')
      break
    case 'n':
      void nextArticle()
      break
    case 'p':
      void previousArticle()
      break
    case 'z':
      void undoDecision()
      break
  }
}

let started = false
// Wait until the user's role is known before loading the reviewer queue
watch(
  roleKnown,
  async (known) => {
    if (!known || started) return
    started = true
    if (canReview.value) await loadNextUnscreened()
  },
  { immediate: true }
)

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  await criteriaStore.fetchCriteria(projectId.value)
  await screeningStore.fetchStats(projectId.value)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

// Start each article at the top of the reading pane
watch(
  () => article.value?.id,
  async () => {
    await nextTick()
    articlePane.value?.scrollTo({ top: 0 })
  }
)

const decisionLabel = (d: ScreeningDecisionType) => d.charAt(0).toUpperCase() + d.slice(1)
</script>

<template>
  <div class="flex flex-col gap-3 lg:h-[calc(100vh-12.5rem)] lg:min-h-[32rem]">
    <ScreeningToolbar
      :project-id="projectId"
      :stage="stage"
      :stats="stats"
      :can-run="canReview"
      class="shrink-0"
      @update:stage="setStage"
      @finished="onBatchFinished"
    />

    <Card v-if="roleKnown && !canReview" class="p-6 text-center text-sm text-muted-foreground">
      You have view-only access to this project. Ask the owner for the reviewer role to screen articles.
    </Card>

    <!-- Screening workspace: article on the left, decision rail on the right -->
    <div
      v-else-if="article"
      class="grid gap-3 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_24rem] xl:grid-cols-[minmax(0,1fr)_28rem]"
    >
      <!-- Left: the article (scrolls on its own on large screens) -->
      <div ref="articlePane" class="min-w-0 space-y-4 lg:h-full lg:overflow-y-auto lg:pr-1">
        <Card class="p-6">
          <div class="space-y-4">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <h1 class="min-w-0 flex-1 break-words text-2xl font-bold" data-testid="article-title">
                {{ article.title || 'Untitled' }}
              </h1>
              <Badge>{{ article.current_stage }}</Badge>
            </div>

            <div v-if="article.authors.length > 0" class="text-muted-foreground">
              {{ article.authors.join(', ') }}
            </div>

            <div class="flex gap-4 text-sm text-muted-foreground">
              <span v-if="article.year">{{ article.year }}</span>
              <span v-if="article.journal">{{ article.journal }}</span>
            </div>

            <div v-if="article.abstract" class="mt-4">
              <h2 class="mb-2 text-lg font-semibold">Abstract</h2>
              <p class="max-w-4xl leading-relaxed text-muted-foreground">{{ article.abstract }}</p>
            </div>

            <div v-if="article.keywords.length > 0" class="mt-4">
              <h2 class="mb-2 text-lg font-semibold">Keywords</h2>
              <div class="flex flex-wrap gap-2">
                <Badge v-for="keyword in article.keywords" :key="keyword" variant="outline">
                  {{ keyword }}
                </Badge>
              </div>
            </div>
          </div>
        </Card>

        <FullTextPanel
          v-if="article.current_stage === 'full_text' || article.full_text_content"
          :article="article"
          height-class="max-h-[70vh] lg:max-h-[calc(100vh-17rem)]"
          pdf-height-class="h-[70vh] lg:h-[calc(100vh-17rem)]"
          @uploaded="refreshArticle"
        />
      </div>

      <!-- Right: decision rail. Verdict and criteria scroll; the decision controls stay in view. -->
      <Card class="flex min-w-0 flex-col overflow-hidden lg:h-full" data-testid="decision-rail">
        <div class="shrink-0 space-y-3 border-b p-4">
          <AiVerdict
            :decision="aiDecision"
            :loading="aiScreeningLoading"
            :can-run="canReview"
            @screen="triggerAiScreening"
          />
          <div v-if="myDecision" class="flex items-center gap-2 text-sm">
            <Badge variant="secondary" data-testid="my-decision">
              Your decision: {{ decisionLabel(myDecision) }}
            </Badge>
          </div>
        </div>

        <div class="p-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
          <CriteriaEvaluationList
            :inclusion="criteriaStore.inclusionCriteria"
            :exclusion="criteriaStore.exclusionCriteria"
            :evaluations="evaluations"
          />
        </div>

        <div class="shrink-0 space-y-3 border-t bg-card p-4">
          <div class="space-y-1.5">
            <Label for="reasoning">Reasoning (Optional)</Label>
            <Textarea id="reasoning" v-model="reasoning" placeholder="Add notes about your decision" :rows="1" />
          </div>

          <div class="grid grid-cols-3 gap-2">
            <Button
              :disabled="submitting"
              class="bg-green-600 px-2 text-white hover:bg-green-700"
              @click="submitDecision('include')"
            >
              Include (I)
            </Button>
            <Button :disabled="submitting" variant="outline" class="px-2" @click="submitDecision('uncertain')">
              Uncertain (U)
            </Button>
            <Button :disabled="submitting" variant="destructive" class="px-2" @click="submitDecision('exclude')">
              Exclude (E)
            </Button>
          </div>

          <div class="flex justify-between gap-2">
            <Button variant="ghost" size="sm" :disabled="pos <= 0 || submitting" @click="previousArticle">
              Previous (P)
            </Button>
            <Button variant="ghost" size="sm" :disabled="submitting" @click="nextArticle">Next (N)</Button>
          </div>

          <ShortcutLegend />
        </div>
      </Card>
    </div>

    <div v-else-if="screeningStore.loading" class="py-12 text-center">
      <p class="text-muted-foreground">Loading next article...</p>
    </div>

    <Card v-else-if="roleKnown" class="p-12 text-center">
      <h2 class="mb-2 text-2xl font-bold">No more articles to screen</h2>
      <p class="text-muted-foreground">
        You've completed screening all available articles at this stage.
      </p>
    </Card>
  </div>
</template>
