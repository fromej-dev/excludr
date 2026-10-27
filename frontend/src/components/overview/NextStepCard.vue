<script setup lang="ts">
import type { NextStep } from '@/utils/nextStep'
import Button from '@/components/ui/Button.vue'

interface Props {
  step: NextStep | null
}

defineProps<Props>()

const emit = defineEmits<{ anchor: [id: string]; retry: [] }>()

const isDone = (kind: string) => kind === 'complete'
const isWaiting = (kind: string) => kind === 'waiting' || kind === 'unavailable'

</script>

<template>
  <section
    class="rounded-lg border p-5 shadow-sm"
    :class="
      step && isDone(step.kind)
        ? 'border-include/40 bg-include-soft text-include-soft-foreground'
        : step && isWaiting(step.kind)
          ? 'bg-card text-card-foreground'
          : 'border-ai/40 bg-ai-soft text-ai-soft-foreground'
    "
    aria-labelledby="next-step-heading"
    data-testid="next-step"
  >
    <p id="next-step-heading" class="text-xs font-semibold uppercase tracking-wider opacity-80">
      {{ step && isWaiting(step.kind) ? 'Status' : 'Next step' }}
    </p>
    <div v-if="!step" class="mt-2 h-12 animate-pulse rounded bg-foreground/10" role="status" aria-label="Loading next step" />
    <div v-else class="mt-1 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <h2 class="text-xl font-semibold" data-testid="next-step-title">{{ step.title }}</h2>
        <p class="mt-1 text-sm opacity-90">{{ step.description }}</p>
      </div>
      <Button
        v-if="step.kind === 'unavailable'"
        variant="outline"
        class="shrink-0"
        data-testid="next-step-retry"
        @click="emit('retry')"
      >
        Retry
      </Button>
      <template v-if="step.action">
        <Button v-if="step.action.target.type === 'anchor'" class="shrink-0" data-testid="next-step-action" @click="emit('anchor', step.action.target.id)">
          {{ step.action.label }}
        </Button>
        <router-link
          v-else
          :to="{
            name: step.action.target.name,
            params: $route.params,
            query: step.action.target.query,
          }"
          class="inline-flex h-10 shrink-0 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          data-testid="next-step-action"
        >
          {{ step.action.label }}
        </router-link>
      </template>
    </div>
  </section>
</template>
