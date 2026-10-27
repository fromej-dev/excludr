<script setup lang="ts">
interface Shortcut {
  key: string
  label: string
}

const shortcuts: Shortcut[] = [
  { key: 'I', label: 'Include' },
  { key: 'E', label: 'Exclude' },
  { key: 'U', label: 'Uncertain' },
  { key: 'N', label: 'Next' },
  { key: 'P', label: 'Previous' },
  { key: 'Z', label: 'Undo' },
]
</script>

<template>
  <div class="space-y-1.5" data-testid="shortcut-legend">
    <p class="text-xs text-muted-foreground">Use keyboard shortcuts (disabled while typing):</p>
    <ul class="flex flex-wrap gap-x-3 gap-y-1">
      <li v-for="s in shortcuts" :key="s.key" class="flex items-center gap-1 text-xs text-muted-foreground">
        <kbd
          class="inline-flex h-5 min-w-5 items-center justify-center rounded border bg-muted px-1 font-mono text-[11px] font-semibold text-foreground"
        >
          {{ s.key }}
        </kbd>
        <span>{{ s.label }}</span>
      </li>
    </ul>
  </div>
</template>
