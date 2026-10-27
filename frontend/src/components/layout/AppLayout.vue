<script setup lang="ts">
import AppHeader from './AppHeader.vue'

interface Props {
  /** Use the full viewport width instead of the centered container. */
  fullWidth?: boolean
}

withDefaults(defineProps<Props>(), { fullWidth: false })
</script>

<template>
  <div class="min-h-screen bg-background">
    <AppHeader />
    <main :class="fullWidth ? 'w-full px-4 py-4' : 'container mx-auto px-4 py-8'">
      <slot />
    </main>
  </div>
</template>
