<script setup lang="ts">
import { computed } from 'vue'
import type { Article, ArticleSortField, ArticleStatus, SortOrder } from '@/types'
import Badge from '@/components/ui/Badge.vue'

type BadgeVariant = InstanceType<typeof Badge>['$props']['variant']

interface Props {
  articles: Article[]
  loading: boolean
  sort: ArticleSortField | ''
  order: SortOrder
  selected: Set<number>
  selectable: boolean
  /** Rows to render as skeletons while loading. */
  skeletonRows?: number
}

const props = withDefaults(defineProps<Props>(), { skeletonRows: 8 })

const emit = defineEmits<{
  open: [articleId: number]
  sort: [field: ArticleSortField]
  'toggle-row': [articleId: number]
  'toggle-all': [checked: boolean]
}>()

const statusVariants: Record<ArticleStatus, BadgeVariant> = {
  imported: 'outline',
  screening: 'secondary',
  awaiting_full_text: 'uncertain',
  full_text_retrieved: 'secondary',
  included: 'include',
  excluded: 'exclude',
}

// Pipeline state shown in the single Status column; included/excluded double as the final decision.
const statusLabels: Record<ArticleStatus, string> = {
  imported: 'Imported',
  screening: 'Title/abstract',
  awaiting_full_text: 'Awaiting full text',
  full_text_retrieved: 'Full text',
  included: 'Included',
  excluded: 'Excluded',
}

const statusLabel = (status: ArticleStatus) => statusLabels[status] ?? status.replace(/_/g, ' ')

const showSkeleton = computed(() => props.loading && props.articles.length === 0)

const allSelected = computed(
  () => props.articles.length > 0 && props.articles.every((a) => props.selected.has(a.id)),
)
const someSelected = computed(() => !allSelected.value && props.articles.some((a) => props.selected.has(a.id)))

const ariaSort = (field: ArticleSortField): 'ascending' | 'descending' | 'none' =>
  props.sort === field ? (props.order === 'asc' ? 'ascending' : 'descending') : 'none'

const secondary = (a: Article) => {
  const authors = a.authors ?? []
  const names = authors.slice(0, 1).join(', ')
  const author = names ? (authors.length > 1 ? `${names} et al.` : names) : ''
  return [author, a.journal].filter(Boolean).join(' · ')
}

const checkboxClass =
  'h-4 w-4 shrink-0 rounded border border-input accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
const thClass = 'px-3 py-2 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground'
</script>

<template>
  <div
    class="overflow-x-auto rounded-lg border bg-card text-card-foreground shadow-sm transition-opacity"
    :class="loading && !showSkeleton ? 'opacity-60' : ''"
  >
    <table role="table" class="block w-full text-sm md:table" :aria-busy="loading">
      <caption class="sr-only">
        Articles
      </caption>
      <thead role="rowgroup" class="hidden border-b bg-muted/50 md:table-header-group">
        <tr role="row" class="md:table-row">
          <th v-if="selectable" role="columnheader" scope="col" class="w-10 px-3 py-2">
            <input
              type="checkbox"
              :class="checkboxClass"
              aria-label="Select all articles on this page"
              :checked="allSelected"
              :indeterminate="someSelected"
              :disabled="articles.length === 0"
              data-testid="select-all"
              @change="emit('toggle-all', ($event.target as HTMLInputElement).checked)"
            />
          </th>
          <th
            v-for="col in [
              { field: 'title', text: 'Title' },
              { field: 'year', text: 'Year' },
              { field: 'status', text: 'Status' },
            ] as { field: ArticleSortField; text: string }[]"
            :key="col.field"
            role="columnheader"
            scope="col"
            :aria-sort="ariaSort(col.field)"
            :class="[thClass, col.field === 'title' ? 'w-full' : '']"
          >
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded uppercase tracking-wide hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :data-testid="`sort-${col.field}`"
              @click="emit('sort', col.field)"
            >
              {{ col.text }}
              <span aria-hidden="true" class="w-3 text-center" :class="sort === col.field ? 'text-foreground' : 'opacity-40'">
                {{ sort === col.field ? (order === 'asc' ? '↑' : '↓') : '↕' }}
              </span>
            </button>
          </th>
          <th role="columnheader" scope="col" :class="thClass">Full text</th>
        </tr>
      </thead>

      <tbody role="rowgroup" class="block divide-y md:table-row-group">
        <template v-if="showSkeleton">
          <tr
            v-for="n in skeletonRows"
            :key="`sk-${n}`"
            role="row"
            class="flex animate-pulse flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3 md:table-row"
            data-testid="article-skeleton"
            aria-hidden="true"
          >
            <td v-if="selectable" role="cell" class="md:table-cell md:px-3 md:py-3">
              <div class="h-4 w-4 rounded bg-muted" />
            </td>
            <td role="cell" class="min-w-0 flex-1 basis-3/4 md:table-cell md:px-3 md:py-3">
              <div class="h-4 w-3/4 rounded bg-muted" />
              <div class="mt-2 h-3 w-1/3 rounded bg-muted" />
            </td>
            <td role="cell" class="md:table-cell md:px-3 md:py-3"><div class="h-4 w-10 rounded bg-muted" /></td>
            <td role="cell" class="md:table-cell md:px-3 md:py-3"><div class="h-5 w-20 rounded-full bg-muted" /></td>
            <td role="cell" class="md:table-cell md:px-3 md:py-3"><div class="h-5 w-16 rounded-full bg-muted" /></td>
          </tr>
        </template>

        <template v-else>
          <tr
            v-for="article in articles"
            :key="article.id"
            role="row"
            tabindex="0"
            :aria-selected="selectable ? selected.has(article.id) : undefined"
            class="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-3 transition-colors hover:bg-accent/60 focus-visible:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring md:table-row md:px-0 md:py-0"
            :class="selected.has(article.id) ? 'bg-accent/40' : ''"
            data-testid="article-card"
            @click="emit('open', article.id)"
            @keydown.enter.self.prevent="emit('open', article.id)"
          >
            <td v-if="selectable" role="cell" class="md:table-cell md:px-3 md:py-3" @click.stop>
              <input
                type="checkbox"
                :class="checkboxClass"
                :aria-label="`Select ${article.title || 'untitled article'}`"
                :checked="selected.has(article.id)"
                data-testid="row-select"
                @change="emit('toggle-row', article.id)"
              />
            </td>

            <td role="cell" class="min-w-0 flex-1 basis-[calc(100%-2.5rem)] md:table-cell md:w-full md:max-w-0 md:px-3 md:py-3">
              <div class="line-clamp-2 font-medium leading-snug" data-testid="article-card-title">
                {{ article.title || 'Untitled' }}
              </div>
              <div v-if="secondary(article)" class="mt-0.5 truncate text-xs text-muted-foreground">
                {{ secondary(article) }}
              </div>
            </td>

            <td
              role="cell"
              class="tabular-nums text-muted-foreground md:table-cell md:px-3 md:py-3"
              :class="selectable ? 'ml-7 md:ml-0' : ''"
            >
              {{ article.year ?? '—' }}
            </td>

            <td role="cell" class="md:table-cell md:whitespace-nowrap md:px-3 md:py-3">
              <Badge
                :variant="statusVariants[article.status] ?? 'outline'"
                :glyph="article.status === 'included' || article.status === 'excluded'"
                data-testid="article-status"
              >
                {{ statusLabel(article.status) }}
              </Badge>
            </td>

            <td role="cell" class="md:table-cell md:whitespace-nowrap md:px-3 md:py-3">
              <Badge v-if="article.full_text_source" variant="secondary" data-testid="fulltext-source">
                {{ article.full_text_source }}
              </Badge>
              <Badge v-else-if="article.full_text_retrieved" variant="secondary">Available</Badge>
              <span v-else class="text-muted-foreground" aria-label="No full text">—</span>
            </td>

          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
