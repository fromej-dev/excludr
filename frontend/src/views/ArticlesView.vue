<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useArticlesStore } from '@/stores/articles'
import { useMembersStore } from '@/stores/members'
import { useWebSocketStore } from '@/stores/websocket'
import { useProjectsStore } from '@/stores/projects'
import { useProjectStatsStore } from '@/stores/projectStats'
import { useBillingStore } from '@/stores/billing'
import { useStoppingRuleStore, refreshAfterRuleChange } from '@/stores/stoppingRule'
import Dialog from '@/components/ui/Dialog.vue'
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
const projectsStore = useProjectsStore()
const statsStore = useProjectStatsStore()
const billingStore = useBillingStore()
const ruleStore = useStoppingRuleStore()
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

onMounted(fetchArticles)

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

const skipSelected = async () => {
  const ids = [...selected.value]
  if (ids.length === 0) return
  if (
    !window.confirm(
      'Move the selected articles past title/abstract screening to full text? ' +
        'Use this for articles already screened elsewhere; it cannot be undone.',
    )
  )
    return
  retrieving.value = true
  const res = await articlesStore.skipTitleAbstract(projectId.value, ids)
  retrieving.value = false
  if (!res) {
    wsStore.addNotification(error.value ?? 'Failed to move articles to full text', 'error')
  } else if (res.moved === 0) {
    wsStore.addNotification('None of the selected articles are waiting for title/abstract screening', 'info')
  } else {
    wsStore.addNotification(`Moved ${res.moved} of ${ids.length} selected articles to full text`, 'success')
    selected.value = new Set()
    await fetchArticles()
  }
}

const showRelevance = computed(
  () => !!projectsStore.currentProject?.prioritized_screening || articles.value.some((a) => a.relevance_score != null)
)

// Owner: put the records closed by the stopping rule back into screening
const notScreened = computed(() => statsStore.stats?.not_screened_stopping_rule ?? 0)
const readOnly = computed(() => !!billingStore.status?.read_only)
const reopenOpen = ref(false)
const reopening = ref(false)
const reopenError = ref<string | null>(null)

const openReopen = () => {
  reopenError.value = null
  reopenOpen.value = true
}

const reopenAll = async () => {
  reopening.value = true
  reopenError.value = null
  const outcome = await ruleStore.reopen(projectId.value)
  reopening.value = false
  if (outcome.ok) {
    reopenOpen.value = false
    wsStore.addNotification(`${outcome.result.reopened} records reopened for screening`, 'info')
    await Promise.all([refreshAfterRuleChange(projectId.value), fetchArticles()])
    return
  }
  reopenError.value = outcome.message
  if (outcome.status === 409) {
    // Nothing was closed any more: refresh the numbers and close
    await refreshAfterRuleChange(projectId.value)
    reopenOpen.value = false
    await fetchArticles()
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
      :show-relevance="showRelevance"
      @update="update"
      @clear="clearFilters"
    />

    <div v-if="isOwner" class="flex flex-wrap items-center justify-end gap-4">
      <Button
        v-if="notScreened > 0 && !readOnly"
        variant="outline"
        size="sm"
        data-testid="reopen-not-screened"
        @click="openReopen"
      >
        Reopen {{ notScreened }} not-screened records
      </Button>
      <router-link
        :to="{ name: 'project-pdf-upload', params: { id: projectId } }"
        class="text-sm font-medium text-primary hover:underline"
        data-testid="upload-pdfs-link"
      >
        Upload full-text PDFs
      </router-link>
    </div>

    <ArticlesBulkBar
      v-if="isOwner && selected.size > 0"
      :count="selected.size"
      :busy="retrieving"
      @retrieve="retrieveSelected"
      @skip-title-abstract="skipSelected"
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
        :show-relevance="showRelevance"
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

    <Dialog v-model:open="reopenOpen" title="Reopen not-screened records">
      <div class="space-y-3 text-sm" data-testid="reopen-dialog">
        <p>
          Put the {{ notScreened }} records closed by the stopping rule back into title/abstract
          screening? They return to the queue and are re-ranked. This undoes the application: the
          streak is back to what it was, and the PRISMA box and methods text are updated.
        </p>
        <p v-if="reopenError" role="alert" class="text-destructive" data-testid="reopen-error">
          {{ reopenError }}
        </p>
        <div class="flex justify-end gap-2 pt-2">
          <Button variant="outline" @click="reopenOpen = false">Cancel</Button>
          <Button :disabled="reopening" data-testid="reopen-confirm" @click="reopenAll">
            Reopen {{ notScreened }} records
          </Button>
        </div>
      </div>
    </Dialog>
  </div>
</template>
