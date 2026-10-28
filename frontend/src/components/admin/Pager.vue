<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps<{ page: number; pageSize: number; total: number }>()
const emit = defineEmits<{ 'update:page': [page: number] }>()

const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const first = computed(() => (props.total ? (props.page - 1) * props.pageSize + 1 : 0))
const last = computed(() => Math.min(props.page * props.pageSize, props.total))
</script>

<template>
  <div class="flex items-center justify-between gap-4 text-sm text-muted-foreground">
    <span>{{ first }}–{{ last }} of {{ total.toLocaleString('en') }}</span>
    <div class="flex gap-2">
      <Button size="sm" variant="outline" :disabled="page <= 1" @click="emit('update:page', page - 1)">
        Previous
      </Button>
      <Button size="sm" variant="outline" :disabled="page >= pages" @click="emit('update:page', page + 1)">
        Next
      </Button>
    </div>
  </div>
</template>
