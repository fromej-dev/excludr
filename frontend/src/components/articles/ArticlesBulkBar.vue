<script setup lang="ts">
import Button from '@/components/ui/Button.vue'

interface Props {
  count: number
  busy: boolean
}

defineProps<Props>()
defineEmits<{
  retrieve: []
  'skip-title-abstract': []
  clear: []
}>()
</script>

<template>
  <div
    class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ai/40 bg-ai-soft px-4 py-2 text-ai-soft-foreground"
    role="region"
    aria-label="Bulk actions"
    data-testid="bulk-bar"
  >
    <p class="text-sm font-medium" aria-live="polite">{{ count }} selected</p>
    <div class="flex items-center gap-2">
      <Button size="sm" :disabled="busy" data-testid="bulk-retrieve" @click="$emit('retrieve')">
        {{ busy ? 'Starting...' : 'Retrieve full text' }}
      </Button>
      <Button
        size="sm"
        variant="outline"
        :disabled="busy"
        title="For articles already screened at title/abstract elsewhere"
        data-testid="bulk-skip-title-abstract"
        @click="$emit('skip-title-abstract')"
      >
        Move to full text
      </Button>
      <Button size="sm" variant="ghost" @click="$emit('clear')">Deselect</Button>
    </div>
  </div>
</template>
