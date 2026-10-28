<script setup lang="ts">
import { computed } from 'vue'
import type { NotificationLevel } from '@/types'

interface Props {
  message: string
  level?: NotificationLevel
  /** Optional action button label (emits `action`). */
  actionLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  level: 'info',
})

const emit = defineEmits<{
  close: []
  action: []
}>()

const levelStyles = computed(() => {
  const baseStyles = 'rounded-lg border p-4 shadow-lg transition-all'

  switch (props.level) {
    case 'success':
      return `${baseStyles} bg-include-soft border-include/40 text-include-soft-foreground`
    case 'warning':
      return `${baseStyles} bg-uncertain-soft border-uncertain/60 text-uncertain-soft-foreground`
    case 'error':
      return `${baseStyles} bg-exclude-soft border-exclude/60 text-exclude-soft-foreground`
    case 'info':
    default:
      return `${baseStyles} bg-ai-soft border-ai/40 text-ai-soft-foreground`
  }
})

const iconStyles = computed(() => {
  switch (props.level) {
    case 'success':
      return 'text-include-soft-foreground'
    case 'warning':
      return 'text-uncertain-soft-foreground'
    case 'error':
      return 'text-exclude-soft-foreground'
    case 'info':
    default:
      return 'text-ai-soft-foreground'
  }
})

const icon = computed(() => {
  switch (props.level) {
    case 'success':
      return '✓'
    case 'warning':
      return '⚠'
    case 'error':
      return '✕'
    case 'info':
    default:
      return 'ℹ'
  }
})
</script>

<template>
  <div :class="levelStyles" role="alert">
    <div class="flex items-start gap-3">
      <span :class="iconStyles" aria-hidden="true" class="text-xl font-bold flex-shrink-0">{{ icon }}</span>
      <p class="flex-1 text-sm">{{ message }}</p>
      <button
        v-if="actionLabel"
        type="button"
        class="flex-shrink-0 rounded-md border border-current/30 px-2 py-0.5 text-xs font-semibold hover:bg-foreground/10 transition-colors"
        @click="emit('action')"
      >
        {{ actionLabel }}
      </button>
      <button
        @click="emit('close')"
        class="flex-shrink-0 opacity-70 hover:opacity-100 transition-colors"
        aria-label="Close notification"
      >
        <span class="text-lg">×</span>
      </button>
    </div>
  </div>
</template>
