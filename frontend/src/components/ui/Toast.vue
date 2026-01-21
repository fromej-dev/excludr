<script setup lang="ts">
import { computed } from 'vue'
import type { NotificationLevel } from '@/types'

interface Props {
  message: string
  level?: NotificationLevel
}

const props = withDefaults(defineProps<Props>(), {
  level: 'info',
})

const emit = defineEmits<{
  close: []
}>()

const levelStyles = computed(() => {
  const baseStyles = 'rounded-lg border p-4 shadow-lg transition-all'

  switch (props.level) {
    case 'success':
      return `${baseStyles} bg-green-50 border-green-200 text-green-900`
    case 'warning':
      return `${baseStyles} bg-yellow-50 border-yellow-200 text-yellow-900`
    case 'error':
      return `${baseStyles} bg-red-50 border-red-200 text-red-900`
    case 'info':
    default:
      return `${baseStyles} bg-blue-50 border-blue-200 text-blue-900`
  }
})

const iconStyles = computed(() => {
  switch (props.level) {
    case 'success':
      return 'text-green-500'
    case 'warning':
      return 'text-yellow-500'
    case 'error':
      return 'text-red-500'
    case 'info':
    default:
      return 'text-blue-500'
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
      <span :class="iconStyles" class="text-xl font-bold flex-shrink-0">{{ icon }}</span>
      <p class="flex-1 text-sm">{{ message }}</p>
      <button
        @click="emit('close')"
        class="flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
        aria-label="Close notification"
      >
        <span class="text-lg">×</span>
      </button>
    </div>
  </div>
</template>
