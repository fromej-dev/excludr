<script setup lang="ts">
import { inject, computed, type ComputedRef } from 'vue'

interface Props {
  value: string
}

const props = defineProps<Props>()

const activeTab = inject<ComputedRef<string>>('activeTab')

const isActive = computed(() => activeTab?.value === props.value)
</script>

<template>
  <div
    v-if="isActive"
    class="mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
  >
    <slot />
  </div>
</template>
