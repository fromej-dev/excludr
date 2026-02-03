<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  value: number // 0-100
  variant?: 'default' | 'success' | 'warning' | 'destructive'
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'md',
})

const heightClass = computed(() => {
  const sizes = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  }
  return sizes[props.size]
})

const colorClass = computed(() => {
  const variants = {
    default: 'bg-primary',
    success: 'bg-green-600',
    warning: 'bg-yellow-600',
    destructive: 'bg-red-600',
  }
  return variants[props.variant]
})
</script>

<template>
  <div class="w-full bg-secondary rounded-full overflow-hidden" :class="heightClass">
    <div
      :class="[heightClass, colorClass]"
      :style="{ width: `${Math.min(100, Math.max(0, value))}%` }"
      class="transition-all duration-300"
    />
  </div>
</template>
