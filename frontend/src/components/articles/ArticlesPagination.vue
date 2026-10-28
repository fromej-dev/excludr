<script setup lang="ts">
import { computed } from 'vue'
import Select from '@/components/ui/Select.vue'
import Label from '@/components/ui/Label.vue'
import Button from '@/components/ui/Button.vue'
import { PAGE_SIZES } from './useArticleListQuery'

interface Props {
  page: number
  perPage: number
  total: number
  pages: number
  count: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:page': [page: number]
  'update:perPage': [perPage: number]
}>()

const sizeOptions = PAGE_SIZES.map((n) => ({ value: n, label: String(n) }))

const from = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.perPage + 1))
const to = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.perPage + props.count))
const lastPage = computed(() => Math.max(props.pages, 1))
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3" data-testid="articles-pagination">
    <p class="text-sm text-muted-foreground" data-testid="articles-range">
      Showing {{ from }}–{{ to }} of {{ total }}
    </p>

    <div class="flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-2">
        <Label for="page-size" class="whitespace-nowrap">Per page</Label>
        <Select
          id="page-size"
          class="!w-20"
          :model-value="perPage"
          :options="sizeOptions"
          @update:model-value="emit('update:perPage', Number($event))"
        />
      </div>

      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" :disabled="page <= 1" @click="emit('update:page', page - 1)">
          Previous
        </Button>
        <span class="whitespace-nowrap text-sm tabular-nums" aria-live="polite">Page {{ page }} of {{ lastPage }}</span>
        <Button variant="outline" size="sm" :disabled="page >= lastPage" @click="emit('update:page', page + 1)">
          Next
        </Button>
      </div>
    </div>
  </div>
</template>
