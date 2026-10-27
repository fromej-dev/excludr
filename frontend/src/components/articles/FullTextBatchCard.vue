<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFulltextBatchStore } from '@/stores/fulltextBatch'
import { useWebSocketStore } from '@/stores/websocket'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Progress from '@/components/ui/Progress.vue'

interface Props {
  projectId: number
  /** Owner only. */
  canRun: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ finished: [] }>()

const batch = useFulltextBatchStore()
const wsStore = useWebSocketStore()
const { running, starting, retrieved, errors, total, percent, error } = storeToRefs(batch)

onMounted(() => batch.subscribe(props.projectId, () => emit('finished')))
onUnmounted(() => batch.unsubscribe())

const run = async () => {
  const res = await batch.start(props.projectId)
  if (!res) {
    wsStore.addNotification(error.value ?? 'Failed to start full-text retrieval', 'error')
  } else if (res.count === 0) {
    wsStore.addNotification('No articles are waiting for a full text', 'info')
  } else {
    wsStore.addNotification(`Full-text retrieval started for ${res.count} articles`, 'success')
  }
}
</script>

<template>
  <Card class="p-4 space-y-3" data-testid="fulltext-batch-card">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="font-semibold">Full-text retrieval</h3>
        <p class="text-xs text-muted-foreground">
          Fetches open-access PDFs (Unpaywall, PMC, Europe PMC) for articles awaiting full text.
        </p>
      </div>
      <Button
        v-if="canRun"
        size="sm"
        variant="outline"
        :disabled="starting || running"
        data-testid="retrieve-fulltexts"
        @click="run"
      >
        {{ starting ? 'Starting...' : running ? 'Retrieving...' : 'Retrieve full texts' }}
      </Button>
    </div>

    <div v-if="running || total > 0" class="space-y-1" data-testid="fulltext-progress">
      <Progress :value="percent" :variant="errors > 0 ? 'warning' : 'default'" />
      <p class="text-xs text-muted-foreground">
        {{ retrieved + errors }} / {{ total }} processed - {{ retrieved }} retrieved
        <template v-if="errors > 0"> - {{ errors }} not found</template>
        <template v-if="!running"> - complete</template>
      </p>
    </div>
  </Card>
</template>
