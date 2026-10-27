<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
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
import AiDecisionPanel from '@/components/screening/AiDecisionPanel.vue'
import AiBatchCard from '@/components/screening/AiBatchCard.vue'
import ShortcutLegend from '@/components/screening/ShortcutLegend.vue'
import FullTextPanel from '@/components/articles/FullTextPanel.vue'

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
const stageTabs: Array<{ value: 'title_abstract' | 'full_text'; label: string }> = [
  { value: 'title_abstract', label: 'Title / abstract' },
  { value: 'full_text', label: 'Full text' },
]
const reasoning = ref('')
const submitting = ref(false)
const myDecision = ref<ScreeningDecisionType | null>(null)

// Articles visited this session, so P/N can step back and forth
const history = ref<number[]>([])
const pos = ref(-1)

const stats = computed(() => screeningStore.stats)

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
  await screeningStore.fetchStats(projectId.value)
  if (pos.value < history.value.length - 1) {
    await goTo(pos.value + 1)
  } else {
    await loadNextUnscreened()
  }
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

const decisionLabel = (d: ScreeningDecisionType) => d.charAt(0).toUpperCase() + d.slice(1)
</script>

<template>
  <div class="space-y-6">
    <div class="grid gap-4 lg:grid-cols-3">
      <!-- Stats Card -->
      <Card v-if="stats" class="p-6 lg:col-span-2">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 class="text-lg font-semibold">Screening Progress</h2>
          <div class="inline-flex rounded-md bg-muted p-1" role="tablist" aria-label="Screening stage">
            <button
              v-for="t in stageTabs"
              :key="t.value"
              type="button"
              role="tab"
              :aria-selected="stage === t.value"
              :class="[
                'rounded-sm px-3 py-1 text-xs font-medium transition-all',
                stage === t.value ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="setStage(t.value)"
            >
              {{ t.label }}
            </button>
          </div>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p class="text-2xl font-bold">{{ stats.total_articles }}</p>
            <p class="text-sm text-muted-foreground">Total</p>
          </div>
          <div>
            <p class="text-2xl font-bold">{{ stats.screened_title_abstract }}</p>
            <p class="text-sm text-muted-foreground">Screened</p>
          </div>
          <div>
            <p class="text-2xl font-bold text-green-600">{{ stats.included }}</p>
            <p class="text-sm text-muted-foreground">Included</p>
          </div>
          <div>
            <p class="text-2xl font-bold text-red-600">{{ stats.excluded }}</p>
            <p class="text-sm text-muted-foreground">Excluded</p>
          </div>
        </div>
      </Card>

      <AiBatchCard :project-id="projectId" :can-run="canReview" @finished="onBatchFinished" />
    </div>

    <Card v-if="roleKnown && !canReview" class="p-6 text-center text-sm text-muted-foreground">
      You have view-only access to this project. Ask the owner for the reviewer role to screen articles.
    </Card>

    <!-- Screening workspace -->
    <div v-else-if="article" class="grid gap-4 lg:grid-cols-5">
      <!-- Left: the article -->
      <div class="space-y-4 lg:col-span-3 min-w-0">
        <Card class="p-6">
          <div class="space-y-4">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <h1 class="text-2xl font-bold flex-1 min-w-0 break-words" data-testid="article-title">
                {{ article.title || 'Untitled' }}
              </h1>
              <div class="flex items-center gap-2">
                <Badge>{{ article.current_stage }}</Badge>
                <Badge v-if="myDecision" variant="secondary" data-testid="my-decision">
                  Your decision: {{ decisionLabel(myDecision) }}
                </Badge>
                <Button
                  v-if="!aiDecision && !aiScreeningLoading"
                  variant="outline"
                  size="sm"
                  @click="triggerAiScreening"
                >
                  Screen with AI
                </Button>
              </div>
            </div>

            <div v-if="article.authors.length > 0" class="text-muted-foreground">
              {{ article.authors.join(', ') }}
            </div>

            <div class="flex gap-4 text-sm text-muted-foreground">
              <span v-if="article.year">{{ article.year }}</span>
              <span v-if="article.journal">{{ article.journal }}</span>
            </div>

            <div v-if="article.abstract" class="mt-4">
              <h2 class="text-lg font-semibold mb-2">Abstract</h2>
              <p class="text-muted-foreground leading-relaxed">{{ article.abstract }}</p>
            </div>

            <div v-if="article.keywords.length > 0" class="mt-4">
              <h2 class="text-lg font-semibold mb-2">Keywords</h2>
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
          height-class="max-h-96"
          @uploaded="refreshArticle"
        />

        <!-- Criteria Reference -->
        <div class="grid gap-4 md:grid-cols-2">
          <Card class="p-4">
            <h3 class="font-semibold mb-3 text-green-600">Inclusion Criteria</h3>
            <div class="space-y-2">
              <div v-for="criterion in criteriaStore.inclusionCriteria" :key="criterion.id" class="text-sm">
                <Badge variant="outline" class="mr-2">{{ criterion.code }}</Badge>
                <span>{{ criterion.description }}</span>
              </div>
            </div>
          </Card>

          <Card class="p-4">
            <h3 class="font-semibold mb-3 text-red-600">Exclusion Criteria</h3>
            <div class="space-y-2">
              <div v-for="criterion in criteriaStore.exclusionCriteria" :key="criterion.id" class="text-sm">
                <Badge variant="outline" class="mr-2">{{ criterion.code }}</Badge>
                <span>{{ criterion.description }}</span>
              </div>
            </div>
          </Card>
        </div>
      </div>

      <!-- Right: AI panel and decision (sticky on large screens) -->
      <div class="space-y-4 lg:col-span-2 min-w-0">
        <Card class="p-6 lg:sticky lg:top-20">
          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="reasoning">Reasoning (Optional)</Label>
              <Textarea
                id="reasoning"
                v-model="reasoning"
                placeholder="Add notes about your decision"
                :rows="3"
              />
            </div>

            <div class="flex flex-wrap gap-3 justify-center">
              <Button
                :disabled="submitting"
                class="bg-green-600 hover:bg-green-700 text-white px-6"
                @click="submitDecision('include')"
              >
                Include (I)
              </Button>
              <Button :disabled="submitting" variant="outline" class="px-6" @click="submitDecision('uncertain')">
                Uncertain (U)
              </Button>
              <Button :disabled="submitting" variant="destructive" class="px-6" @click="submitDecision('exclude')">
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

        <AiDecisionPanel :decision="aiDecision" :loading="aiScreeningLoading" />
      </div>
    </div>

    <div v-else-if="screeningStore.loading" class="text-center py-12">
      <p class="text-muted-foreground">Loading next article...</p>
    </div>

    <Card v-else-if="roleKnown" class="p-12 text-center">
      <h2 class="text-2xl font-bold mb-2">No more articles to screen</h2>
      <p class="text-muted-foreground">
        You've completed screening all available articles at this stage.
      </p>
    </Card>
  </div>
</template>
