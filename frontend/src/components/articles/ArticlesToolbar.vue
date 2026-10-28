<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import type { ArticleSortField } from '@/types'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Label from '@/components/ui/Label.vue'
import Button from '@/components/ui/Button.vue'
import type { ArticleListState, FullTextFilter } from './useArticleListQuery'

interface Props {
  state: ArticleListState
  total: number
  hasFilters: boolean
  loading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  update: [patch: Partial<ArticleListState>]
  clear: []
}>()

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'imported', label: 'Imported' },
  { value: 'screening', label: 'Title/abstract' },
  { value: 'awaiting_full_text', label: 'Awaiting full text' },
  { value: 'full_text_retrieved', label: 'Full text' },
  { value: 'included', label: 'Included' },
  { value: 'excluded', label: 'Excluded' },
]

const decisionOptions = [
  { value: '', label: 'All Decisions' },
  { value: 'pending', label: 'Pending' },
  { value: 'included', label: 'Included' },
  { value: 'excluded', label: 'Excluded' },
]

const fullTextOptions = [
  { value: '', label: 'Any' },
  { value: 'has', label: 'Has full text' },
  { value: 'missing', label: 'Missing full text' },
]

const sortOptions = [
  { value: '', label: 'Default order' },
  { value: 'title:asc', label: 'Title A-Z' },
  { value: 'title:desc', label: 'Title Z-A' },
  { value: 'year:desc', label: 'Newest first' },
  { value: 'year:asc', label: 'Oldest first' },
  { value: 'status:asc', label: 'Status A-Z' },
  { value: 'status:desc', label: 'Status Z-A' },
]

// Local text so typing is instant; the URL (and the fetch) follow after a pause.
const searchText = ref(props.state.q)
let timer: ReturnType<typeof setTimeout> | null = null

watch(searchText, (value) => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    if (value.trim() !== props.state.q.trim()) emit('update', { q: value })
  }, 300)
})

// Follow external changes (Clear, back button).
watch(
  () => props.state.q,
  (q) => {
    if (q.trim() !== searchText.value.trim()) searchText.value = q
  },
)

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})

const sortValue = computed(() => (props.state.sort ? `${props.state.sort}:${props.state.order}` : ''))

const onSortChange = (value: string | number) => {
  const [field, order] = String(value).split(':')
  emit('update', {
    sort: (field || '') as ArticleSortField | '',
    order: order === 'desc' ? 'desc' : 'asc',
  })
}

const countLabel = computed(() => `${props.total} ${props.total === 1 ? 'article' : 'articles'}`)
</script>

<template>
  <div class="space-y-3" data-testid="articles-toolbar">
    <div class="flex flex-wrap items-end gap-3">
      <div class="w-full space-y-1.5 md:w-72">
        <Label for="article-search">Search</Label>
        <Input
          id="article-search"
          type="search"
          :model-value="searchText"
          placeholder="Title, author or journal"
          @update:model-value="searchText = String($event)"
        />
      </div>

      <div class="min-w-[9rem] flex-1 space-y-1.5 md:flex-none">
        <Label for="status-filter">Status</Label>
        <Select
          id="status-filter"
          :model-value="state.status"
          :options="statusOptions"
          @update:model-value="emit('update', { status: $event as ArticleListState['status'] })"
        />
      </div>

      <div class="min-w-[9rem] flex-1 space-y-1.5 md:flex-none">
        <Label for="decision-filter">Decision</Label>
        <Select
          id="decision-filter"
          :model-value="state.decision"
          :options="decisionOptions"
          @update:model-value="emit('update', { decision: $event as ArticleListState['decision'] })"
        />
      </div>

      <div class="min-w-[9rem] flex-1 space-y-1.5 md:flex-none">
        <Label for="fulltext-filter">Full text</Label>
        <Select
          id="fulltext-filter"
          :model-value="state.fullText"
          :options="fullTextOptions"
          @update:model-value="emit('update', { fullText: $event as FullTextFilter })"
        />
      </div>

      <div class="w-full space-y-1.5 md:hidden">
        <Label for="article-sort">Sort by</Label>
        <Select id="article-sort" :model-value="sortValue" :options="sortOptions" @update:model-value="onSortChange" />
      </div>

      <Button variant="outline" :disabled="!hasFilters" @click="emit('clear')">Clear filters</Button>
    </div>

    <p class="text-sm text-muted-foreground" aria-live="polite" data-testid="articles-count">
      <template v-if="loading && total === 0">Loading...</template>
      <template v-else>{{ countLabel }}</template>
    </p>
  </div>
</template>
