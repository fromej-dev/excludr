<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAiBatchStore } from '@/stores/aiBatch'
import { useWebSocketStore } from '@/stores/websocket'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Progress from '@/components/ui/Progress.vue'

interface Props {
  projectId: number
  /** Reviewer role or higher. */
  canRun: boolean
  /**
   * Join the project room and listen for batch progress while mounted. Disable when a parent
   * (e.g. the screening toolbar) owns the subscription and this card is only shown on demand.
   */
  manageSubscription?: boolean
}

const props = withDefaults(defineProps<Props>(), { manageSubscription: true })
const emit = defineEmits<{ finished: [] }>()

const aiBatch = useAiBatchStore()
const wsStore = useWebSocketStore()
const { running, starting, screened, errors, total, staleCount, percent, error } = storeToRefs(aiBatch)

const rescreenStale = ref(false)

onMounted(() => {
  if (!props.manageSubscription) return
  aiBatch.subscribe(props.projectId, () => emit('finished'))
  aiBatch.fetchStale(props.projectId)
})

onUnmounted(() => {
  if (!props.manageSubscription) return
  aiBatch.unsubscribe()
})

const run = async () => {
  const res = await aiBatch.start(props.projectId, rescreenStale.value)
  if (!res) {
    wsStore.addNotification(error.value ?? 'Failed to start AI screening', 'error')
  } else if (res.article_count === 0) {
    wsStore.addNotification('No eligible articles for AI screening', 'info')
  } else {
    wsStore.addNotification(`AI screening started for ${res.article_count} articles`, 'success')
  }
}
</script>

<template>
  <Card class="p-4 space-y-3" data-testid="ai-batch-card">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="font-semibold">AI assistant</h3>
        <p class="text-xs text-muted-foreground">Runs in the background; progress updates live.</p>
      </div>
      <Button
        v-if="canRun"
        size="sm"
        variant="outline"
        :disabled="starting || running"
        data-testid="run-ai"
        @click="run"
      >
        {{ starting ? 'Starting...' : running ? 'AI running...' : 'Run AI screening' }}
      </Button>
    </div>

    <label v-if="canRun" class="flex items-center gap-2 text-sm">
      <input v-model="rescreenStale" type="checkbox" class="h-4 w-4 accent-primary" :disabled="running" />
      <span>
        Re-screen stale decisions
        <span class="text-muted-foreground" data-testid="stale-count">
          ({{ staleCount }} outdated by criteria changes)
        </span>
      </span>
    </label>

    <div v-if="running || total > 0" class="space-y-1" data-testid="ai-progress">
      <Progress :value="percent" :variant="errors > 0 ? 'warning' : 'default'" />
      <p class="text-xs text-muted-foreground">
        {{ screened + errors }} / {{ total }} done
        <template v-if="errors > 0"> - {{ errors }} failed</template>
        <template v-if="!running"> - complete</template>
      </p>
    </div>
  </Card>
</template>
