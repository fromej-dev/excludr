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
      'bg-destructive/5 border-destructive/30': tone === 'exclude',
      'bg-green-600/10 border-green-600/40': tone === 'include',
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
