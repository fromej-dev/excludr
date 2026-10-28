<script setup lang="ts">
interface Props {
  title: string
  count: number
  tone?: 'default' | 'exclude' | 'include'
}

withDefaults(defineProps<Props>(), { tone: 'default' })
</script>

<template>
  <div
    class="rounded-md border p-3 text-sm shadow-sm"
    :class="{
      'bg-card': tone === 'default',
      'bg-exclude-soft text-exclude-soft-foreground border-exclude/60': tone === 'exclude',
      'bg-include-soft text-include-soft-foreground border-include/40': tone === 'include',
    }"
  >
    <p class="font-medium leading-snug">
      {{ title }}
      <span class="font-bold">(n = {{ count }})</span>
    </p>
    <div v-if="$slots.default" class="mt-2 text-xs text-muted-foreground space-y-0.5">
      <slot />
    </div>
  </div>
</template>
