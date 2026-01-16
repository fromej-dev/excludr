<script setup lang="ts">
import { ref } from 'vue'
import type { Criterion } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'

interface Props {
  criterion: Criterion
}

defineProps<Props>()

const emit = defineEmits<{
  edit: [criterion: Criterion]
  delete: [criterion: Criterion]
}>()
</script>

<template>
  <Card class="p-4">
    <div class="space-y-3">
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-2">
          <Badge :variant="criterion.type === 'inclusion' ? 'default' : 'secondary'">
            {{ criterion.code }}
          </Badge>
          <Badge v-if="!criterion.is_active" variant="outline">Inactive</Badge>
        </div>
        <div class="flex gap-2">
          <Button variant="ghost" size="sm" @click="$emit('edit', criterion)">
            Edit
          </Button>
          <Button variant="ghost" size="sm" @click="$emit('delete', criterion)">
            Delete
          </Button>
        </div>
      </div>

      <div>
        <p class="text-sm font-medium">{{ criterion.description }}</p>
      </div>

      <div v-if="criterion.rationale" class="text-sm text-muted-foreground">
        <span class="font-medium">Rationale:</span> {{ criterion.rationale }}
      </div>
    </div>
  </Card>
</template>
