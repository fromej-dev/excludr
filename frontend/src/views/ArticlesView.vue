<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useArticlesStore } from '@/stores/articles'
import { useMembersStore } from '@/stores/members'
import { useWebSocketStore } from '@/stores/websocket'
import Button from '@/components/ui/Button.vue'
import ArticlesToolbar from '@/components/articles/ArticlesToolbar.vue'
import ArticlesTable from '@/components/articles/ArticlesTable.vue'
import ArticlesPagination from '@/components/articles/ArticlesPagination.vue'
import ArticlesBulkBar from '@/components/articles/ArticlesBulkBar.vue'
import { useArticleListQuery, toListOptions } from '@/components/articles/useArticleListQuery'

const route = useRoute()
const router = useRouter()
const articlesStore = useArticlesStore()
const membersStore = useMembersStore()
const wsStore = useWebSocketStore()
const { articles, pagination, loading, error } = storeToRefs(articlesStore)
const { isOwner } = storeToRefs(membersStore)

const projectId = computed(() => Number(route.params.id))
const { state, hasFilters, update, clearFilters, toggleSort } = useArticleListQuery()

// Selection (owner bulk actions). Cleared whenever the result set changes.
const selected = ref<Set<number>>(new Set())
const retrieving = ref(false)

// Avoid flashing the empty state (or another project's rows) before the first response.
const hasFetched = ref(false)
articlesStore.articles = []

const fetchArticles = async () => {
  await articlesStore.fetchArticles(projectId.value, toListOptions(state.value))
  hasFetched.value = true
}

// The query string is the single source of truth: any change refetches.
watch(
  () => [route.name, route.params.id, route.query] as const,
  ([name]) => {
    if (name !== 'project-articles') return
    fetchArticles()
  },
  { deep: true },
)

// Filters/sort/page changes invalidate the selection.
watch(
  () => JSON.stringify(route.query),
  () => {
    selected.value = new Set()
  },
)

// Keep the page in range (e.g. after shrinking results or a stale ?page=).
watch(
  () => [loading.value, pagination.value.pages] as const,
  ([isLoading, pages]) => {
    if (!isLoading && pages > 0 && state.value.page > pages) update({ page: pages })
  },
)

// Returning from an article via its "Back" button lands on a bare URL, so remember
// the list query when leaving for a detail page and restore it once.
const RESTORE_KEY = 'excludr_articles_query'

onBeforeRouteLeave((to) => {
  if (to.name === 'article-detail') {
    sessionStorage.setItem(
      RESTORE_KEY,
      JSON.stringify({ projectId: projectId.value, query: route.query }),
    )
  }
})

onMounted(() => {
  const raw = sessionStorage.getItem(RESTORE_KEY)
  sessionStorage.removeItem(RESTORE_KEY)
  if (raw && Object.keys(route.query).length === 0) {
    try {
      const saved = JSON.parse(raw) as { projectId: number; query: Record<string, string> }
      if (saved.projectId === projectId.value && Object.keys(saved.query).length > 0) {
        router.replace({ query: saved.query })
        return
      }
    } catch {
      // Ignore corrupt entries
    }
  }
  fetchArticles()
})

const goToArticle = (articleId: number) => {
  router.push({ name: 'article-detail', params: { id: projectId.value, articleId } })
}

const toggleRow = (id: number) => {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

const toggleAll = (checked: boolean) => {
  selected.value = checked ? new Set(articles.value.map((a) => a.id)) : new Set()
}

const retrieveSelected = async () => {
  const ids = [...selected.value]
  if (ids.length === 0) return
  retrieving.value = true
  const res = await articlesStore.retrieveFulltext(projectId.value, ids)
  retrieving.value = false
  if (!res) {
    wsStore.addNotification(error.value ?? 'Failed to start full-text retrieval', 'error')
  } else if (res.count === 0) {
    wsStore.addNotification('None of the selected articles are awaiting a full text', 'info')
  } else {
    wsStore.addNotification(
      `Full-text retrieval started for ${res.count} of ${ids.length} selected articles`,
      'success',
    )
    selected.value = new Set()
  }
}

const isEmpty = computed(() => hasFetched.value && !loading.value && !error.value && articles.value.length === 0)
</script>

<template>
  <div class="space-y-4">
    <ArticlesToolbar
      :state="state"
      :total="pagination.total"
      :has-filters="hasFilters"
      :loading="loading"
      @update="update"
      @clear="clearFilters"
    />

    <ArticlesBulkBar
      v-if="isOwner && selected.size > 0"
      :count="selected.size"
      :busy="retrieving"
      @retrieve="retrieveSelected"
      @clear="selected = new Set()"
    />

    <p v-if="error" role="alert" class="rounded-md border border-destructive/50 p-3 text-sm text-destructive">
      {{ error }}
    </p>

    <div
      v-if="isEmpty && !hasFilters"
      class="rounded-lg border border-dashed py-14 text-center"
      data-testid="articles-empty"
    >
      <p class="font-medium">No articles found</p>
      <p class="mt-1 text-sm text-muted-foreground">Import a RIS or PubMed file to get started.</p>
      <router-link
        :to="{ name: 'project-overview', params: { id: projectId } }"
        class="mt-4 inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Go to Overview to import
      </router-link>
    </div>

    <div
      v-else-if="isEmpty"
      class="rounded-lg border border-dashed py-14 text-center"
      data-testid="articles-no-matches"
    >
      <p class="font-medium">No articles found</p>
      <p class="mt-1 text-sm text-muted-foreground">Nothing matches the current search and filters.</p>
      <Button class="mt-4" variant="outline" size="sm" @click="clearFilters">Clear all filters</Button>
    </div>

    <template v-else>
      <ArticlesTable
        :articles="articles"
        :loading="loading"
        :sort="state.sort"
        :order="state.order"
        :selected="selected"
        :selectable="isOwner"
        @open="goToArticle"
        @sort="toggleSort"
        @toggle-row="toggleRow"
        @toggle-all="toggleAll"
      />

      <ArticlesPagination
        :page="state.page"
        :per-page="state.perPage"
        :total="pagination.total"
        :pages="pagination.pages"
        :count="articles.length"
        @update:page="update({ page: $event })"
        @update:per-page="update({ perPage: $event })"
      />
    </template>
  </div>
</template>
