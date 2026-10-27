<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import Card from '@/components/ui/Card.vue'

export interface ChecklistItem {
  key: string
  label: string
  done: boolean
  to?: RouteLocationRaw
  anchor?: string
}

interface Props {
  items: ChecklistItem[]
}

defineProps<Props>()
const emit = defineEmits<{ anchor: [id: string] }>()
</script>

<template>
  <Card class="p-5" data-testid="setup-checklist">
    <h2 class="text-lg font-semibold">Setup checklist</h2>
    <ul class="mt-3 space-y-2">
      <li v-for="item in items" :key="item.key" class="flex items-center gap-3 text-sm" :data-testid="`setup-${item.key}`">
        <span
          class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold"
          :class="item.done ? 'border-include bg-include text-include-foreground' : 'border-muted-foreground/50'"
          aria-hidden="true"
          >{{ item.done ? '✓' : '' }}</span
        >
        <component
          :is="item.to ? 'router-link' : 'button'"
          v-bind="item.to ? { to: item.to } : { type: 'button' }"
          class="text-left font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :class="item.done ? 'text-muted-foreground line-through' : 'text-foreground'"
          @click="!item.to && item.anchor && emit('anchor', item.anchor)"
        >
          {{ item.label }}
        </component>
        <span class="sr-only">{{ item.done ? 'Done' : 'To do' }}</span>
      </li>
    </ul>
  </Card>
</template>
