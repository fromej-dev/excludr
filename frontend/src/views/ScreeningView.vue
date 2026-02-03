<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useScreeningStore } from '@/stores/screening'
import { useCriteriaStore } from '@/stores/criteria'
import { useMagicKeys } from '@vueuse/core'
import type { ScreeningDecisionType, ScreeningStage } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Label from '@/components/ui/Label.vue'
import AiDecisionPanel from '@/components/screening/AiDecisionPanel.vue'
import { useWebSocketStore } from '@/stores/websocket'

const route = useRoute()
const screeningStore = useScreeningStore()
const criteriaStore = useCriteriaStore()
const wsStore = useWebSocketStore()

const projectId = computed(() => Number(route.params.id))
const article = computed(() => screeningStore.currentArticle)
const aiDecision = computed(() => screeningStore.aiDecision)
const aiScreeningLoading = computed(() => screeningStore.aiScreeningLoading)

const stage = ref<ScreeningStage>('title_abstract')
const reasoning = ref('')
const submitting = ref(false)

const { i, e, u } = useMagicKeys()

onMounted(async () => {
  // Join project WebSocket room for real-time updates
  wsStore.joinProjectRoom(projectId.value)

  await criteriaStore.fetchCriteria(projectId.value)
  await screeningStore.fetchStats(projectId.value)
  await loadNextArticle()
})

onUnmounted(() => {
  // Leave project WebSocket room
  wsStore.leaveProjectRoom(projectId.value)
})

const loadNextArticle = async () => {
  reasoning.value = ''
  await screeningStore.fetchNextArticle(projectId.value, stage.value)

  // Fetch AI decision for the loaded article if one exists
  if (screeningStore.currentArticle) {
    await screeningStore.fetchAiDecision(projectId.value, screeningStore.currentArticle.id)
  }
}

const submitDecision = async (decision: ScreeningDecisionType) => {
  if (!article.value || submitting.value) return

  submitting.value = true

  await screeningStore.submitDecision(projectId.value, article.value.id, {
    stage: stage.value,
    decision,
    source: 'human',
    reasoning: reasoning.value || undefined,
  })

  submitting.value = false
  await screeningStore.fetchStats(projectId.value)
  await loadNextArticle()
}

const triggerAiScreening = async () => {
  if (!article.value) return

  const result = await screeningStore.triggerAiScreening(projectId.value, article.value.id)
  if (result) {
    wsStore.addNotification('AI screening completed', 'success')
  }
}

const triggerBatchAiScreening = async () => {
  const result = await screeningStore.triggerBatchAiScreening(projectId.value)
  if (result) {
    wsStore.addNotification(
      `Batch AI screening started for ${result.article_count} articles`,
      'success'
    )
  }
}

// Keyboard shortcuts
const handleKeyPress = (decision: ScreeningDecisionType) => {
  if (!submitting.value && article.value) {
    submitDecision(decision)
  }
}

onMounted(() => {
  const handleI = () => handleKeyPress('include')
  const handleE = () => handleKeyPress('exclude')
  const handleU = () => handleKeyPress('uncertain')

  // Use VueUse's magic keys with watchers
  const stopI = () => { if (i.value) handleI() }
  const stopE = () => { if (e.value) handleE() }
  const stopU = () => { if (u.value) handleU() }

  const intervalId = setInterval(() => {
    stopI()
    stopE()
    stopU()
  }, 100)

  onUnmounted(() => {
    clearInterval(intervalId)
  })
})

const stats = computed(() => screeningStore.stats)
</script>

<template>
  <div class="space-y-6">
    <!-- Stats Card -->
    <Card v-if="stats" class="p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Screening Progress</h2>
        <Button
          @click="triggerBatchAiScreening"
          :disabled="aiScreeningLoading"
          variant="outline"
          size="sm"
        >
          {{ aiScreeningLoading ? 'Running...' : 'Run AI Screening (Batch)' }}
        </Button>
      </div>
      <div class="grid grid-cols-4 gap-4">
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

    <!-- Screening Card -->
    <div v-if="article" class="space-y-4">
      <Card class="p-6">
        <div class="space-y-4">
          <div class="flex items-start justify-between gap-4">
            <h1 class="text-2xl font-bold flex-1">{{ article.title || 'Untitled' }}</h1>
            <div class="flex items-center gap-2">
              <Badge>{{ article.current_stage }}</Badge>
              <Button
                v-if="!aiDecision && !aiScreeningLoading"
                @click="triggerAiScreening"
                variant="outline"
                size="sm"
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

      <!-- AI Decision Panel -->
      <AiDecisionPanel :decision="aiDecision" :loading="aiScreeningLoading" />

      <!-- Criteria Reference -->
      <div class="grid gap-4 md:grid-cols-2">
        <Card class="p-4">
          <h3 class="font-semibold mb-3 text-green-600">Inclusion Criteria</h3>
          <div class="space-y-2">
            <div
              v-for="criterion in criteriaStore.inclusionCriteria"
              :key="criterion.id"
              class="text-sm"
            >
              <Badge variant="outline" class="mr-2">{{ criterion.code }}</Badge>
              <span>{{ criterion.description }}</span>
            </div>
          </div>
        </Card>

        <Card class="p-4">
          <h3 class="font-semibold mb-3 text-red-600">Exclusion Criteria</h3>
          <div class="space-y-2">
            <div
              v-for="criterion in criteriaStore.exclusionCriteria"
              :key="criterion.id"
              class="text-sm"
            >
              <Badge variant="outline" class="mr-2">{{ criterion.code }}</Badge>
              <span>{{ criterion.description }}</span>
            </div>
          </div>
        </Card>
      </div>

      <!-- Decision Panel -->
      <Card class="p-6">
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

          <div class="flex gap-3 justify-center">
            <Button
              @click="submitDecision('include')"
              :disabled="submitting"
              class="bg-green-600 hover:bg-green-700 text-white px-8"
            >
              Include (I)
            </Button>
            <Button
              @click="submitDecision('uncertain')"
              :disabled="submitting"
              variant="outline"
              class="px-8"
            >
              Uncertain (U)
            </Button>
            <Button
              @click="submitDecision('exclude')"
              :disabled="submitting"
              variant="destructive"
              class="px-8"
            >
              Exclude (E)
            </Button>
          </div>

          <p class="text-center text-xs text-muted-foreground">
            Use keyboard shortcuts: I (include), E (exclude), U (uncertain)
          </p>
        </div>
      </Card>
    </div>

    <div v-else-if="screeningStore.loading" class="text-center py-12">
      <p class="text-muted-foreground">Loading next article...</p>
    </div>

    <Card v-else class="p-12 text-center">
      <h2 class="text-2xl font-bold mb-2">No more articles to screen</h2>
      <p class="text-muted-foreground">
        You've completed screening all available articles at this stage.
      </p>
    </Card>
  </div>
</template>
