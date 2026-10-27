<script setup lang="ts">
import { computed } from 'vue'

type BadgeVariant =
  | 'default'
  | 'secondary'
  | 'destructive'
  | 'outline'
  | 'include'
  | 'exclude'
  | 'uncertain'
  | 'ai'

interface Props {
  variant?: BadgeVariant
  /** Show the non-colour cue (check / cross / question mark) for decision variants. */
  glyph?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  glyph: true,
})

const classes = computed(() => {
  const base = 'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'

  const variants: Record<BadgeVariant, string> = {
    default: 'border-transparent bg-primary text-primary-foreground hover:bg-primary/80',
    secondary: 'border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80',
    destructive: 'border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80',
    outline: 'text-foreground',
    include: 'border-include/40 bg-include-soft text-include-soft-foreground',
    exclude: 'border-exclude/60 bg-exclude-soft text-exclude-soft-foreground',
    uncertain: 'border-uncertain/60 bg-uncertain-soft text-uncertain-soft-foreground',
    ai: 'border-ai/40 bg-ai-soft text-ai-soft-foreground',
  }

  return `${base} ${variants[props.variant]}`
})

const glyphs: Partial<Record<BadgeVariant, string>> = {
  include: '✓',
  exclude: '✕',
  uncertain: '?',
}

const glyphChar = computed(() => (props.glyph ? glyphs[props.variant] ?? '' : ''))
</script>

<template>
  <div :class="classes">
    <span v-if="glyphChar" aria-hidden="true" class="font-bold leading-none">{{ glyphChar }}</span>
    <slot />
  </div>
</template>
