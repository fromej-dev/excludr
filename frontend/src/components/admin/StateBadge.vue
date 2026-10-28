<script setup lang="ts">
import { computed } from 'vue'
import Badge from '@/components/ui/Badge.vue'

const props = defineProps<{ state: string }>()

const look = computed(() => {
  const states: Record<string, { text: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    free: { text: 'Free', variant: 'secondary' },
    active: { text: 'Active', variant: 'default' },
    expiring: { text: 'Expiring', variant: 'outline' },
    expired: { text: 'Expired', variant: 'destructive' },
    paid: { text: 'Paid', variant: 'default' },
    partially_refunded: { text: 'Partly refunded', variant: 'outline' },
    refunded: { text: 'Refunded', variant: 'destructive' },
  }
  return states[props.state] ?? { text: props.state, variant: 'secondary' as const }
})
</script>

<template>
  <Badge :variant="look.variant">{{ look.text }}</Badge>
</template>
