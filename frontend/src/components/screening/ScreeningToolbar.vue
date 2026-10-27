<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useAiBatchStore } from '@/stores/aiBatch'
import type { ScreeningStats } from '@/types'
import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import Progress from '@/components/ui/Progress.vue'
import AiBatchCard from '@/components/screening/AiBatchCard.vue'

type Stage = 'title_abstract' | 'full_text'

interface Props {
  projectId: number
  stage: Stage
  stats: ScreeningStats | null
  /** Reviewer role or higher. */
  canRun: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:stage': [value: Stage]
  finished: []
}>()

const stageTabs: Array<{ value: Stage; label: string }> = [
  { value: 'title_abstract', label: 'Title / abstract' },
  { value: 'full_text', label: 'Full text' },
]

const aiBatch = useAiBatchStore()
const { running, done, total } = storeToRefs(aiBatch)

// The toolbar owns the batch subscription so progress keeps updating while the dialog is closed
onMounted(() => {
  aiBatch.subscribe(props.projectId, () => emit('finished'))
  aiBatch.fetchStale(props.projectId)
})
onUnmounted(() => aiBatch.unsubscribe())

const aiOpen = ref(false)

/** Screened count for the CURRENT stage. */
const screened = computed(() => {
  if (!props.stats) return 0
  return props.stage === 'full_text' ? props.stats.screened_full_text : props.stats.screened_title_abstract
})
const totalArticles = computed(() => props.stats?.total_articles ?? 0)
const percent = computed(() =>
  totalArticles.value ? Math.round((screened.value / totalArticles.value) * 100) : 0
)
</script>

<template>
  <div
    class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border bg-card px-3 py-2 shadow-sm"
    data-testid="screening-toolbar"
  >
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
        @click="emit('update:stage', t.value)"
      >
        {{ t.label }}
      </button>
    </div>

    <div v-if="stats" class="flex min-w-48 flex-1 items-center gap-3" data-testid="screening-progress">
      <Progress :value="percent" size="sm" class="max-w-xs" />
      <span class="whitespace-nowrap text-sm text-muted-foreground">
        <span class="font-semibold text-foreground" data-testid="screened-count">{{ screened }}</span>
        / {{ totalArticles }} screened
      </span>
    </div>
    <div v-else class="flex-1" />

    <dl v-if="stats" class="flex items-center gap-4 text-sm">
      <div class="flex items-baseline gap-1.5">
        <dd class="font-semibold text-green-600" data-testid="included-count">{{ stats.included }}</dd>
        <dt class="text-muted-foreground">Included</dt>
      </div>
      <div class="flex items-baseline gap-1.5">
        <dd class="font-semibold text-red-600" data-testid="excluded-count">{{ stats.excluded }}</dd>
        <dt class="text-muted-foreground">Excluded</dt>
      </div>
    </dl>

    <Button size="sm" variant="outline" data-testid="ai-batch-open" @click="aiOpen = true">
      <template v-if="running">AI running {{ done }}/{{ total }}</template>
      <template v-else>AI batch</template>
    </Button>

    <Dialog v-model:open="aiOpen">
      <AiBatchCard :project-id="projectId" :can-run="canRun" :manage-subscription="false" class="border-0 shadow-none" />
      <div class="mt-4 flex justify-end">
        <Button size="sm" variant="ghost" @click="aiOpen = false">Close</Button>
      </div>
    </Dialog>
  </div>
</template>
