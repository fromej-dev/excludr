<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Article, PaginatedResponse, PdfArticleChoice as ArticleChoice, PdfMatchCandidate } from '@/types'

interface Props {
  projectId: number
  candidates: PdfMatchCandidate[]
}

const props = defineProps<Props>()
const emit = defineEmits<{ pick: [choice: ArticleChoice]; cancel: [] }>()

const { getRaw } = useApi()
const query = ref('')
const results = ref<ArticleChoice[]>([])
const searching = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let seq = 0

const search = async (term: string) => {
  const mine = ++seq
  searching.value = true
  try {
    const params = new URLSearchParams({
      search: term,
      search_fields: 'title,authors,journal',
      per_page: '8',
    })
    const res = await getRaw<PaginatedResponse<Article>>(`/projects/${props.projectId}/articles?${params}`)
    if (mine !== seq) return
    results.value = res.data.map((a) => ({
      article_id: a.id,
      title: a.title ?? null,
      year: a.year ?? null,
      has_full_text: !!a.full_text_retrieved,
    }))
  } catch {
    if (mine === seq) results.value = []
  } finally {
    if (mine === seq) searching.value = false
  }
}

watch(query, (term) => {
  clearTimeout(timer)
  if (term.trim().length < 2) {
    results.value = []
    return
  }
  timer = setTimeout(() => search(term.trim()), 250)
})

onUnmounted(() => clearTimeout(timer))

const label = (c: ArticleChoice) => `${c.title ?? 'Untitled'}${c.year ? ` (${c.year})` : ''}`
</script>

<template>
  <div class="space-y-2 rounded-md border bg-background p-2" data-testid="pdf-article-picker">
    <input
      v-model="query"
      type="search"
      placeholder="Search articles by title, author or journal"
      aria-label="Search articles"
      class="h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      autofocus
    />
    <ul class="max-h-60 overflow-y-auto text-sm">
      <template v-if="!query.trim()">
        <li v-if="candidates.length === 0" class="px-2 py-1 text-muted-foreground">
          No suggestions; search for the article.
        </li>
        <li v-for="c in candidates" :key="`c-${c.article_id}`">
          <button
            type="button"
            class="w-full rounded px-2 py-1 text-left hover:bg-accent"
            @click="emit('pick', c)"
          >
            {{ label(c) }}
            <span class="text-xs text-muted-foreground">- suggested ({{ c.confidence }})</span>
          </button>
        </li>
      </template>
      <template v-else>
        <li v-if="searching" class="px-2 py-1 text-muted-foreground">Searching...</li>
        <li v-else-if="results.length === 0 && query.trim().length >= 2" class="px-2 py-1 text-muted-foreground">
          No articles found.
        </li>
        <li v-for="r in results" :key="`r-${r.article_id}`">
          <button type="button" class="w-full rounded px-2 py-1 text-left hover:bg-accent" @click="emit('pick', r)">
            {{ label(r) }}
            <span v-if="r.has_full_text" class="text-xs text-muted-foreground">- has full text</span>
          </button>
        </li>
      </template>
    </ul>
    <div class="flex justify-end">
      <button type="button" class="text-xs text-muted-foreground hover:underline" @click="emit('cancel')">
        Cancel
      </button>
    </div>
  </div>
</template>
