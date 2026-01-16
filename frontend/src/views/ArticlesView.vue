<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useArticlesStore } from '@/stores/articles'
import type { ArticleStatus, FinalDecision } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Select from '@/components/ui/Select.vue'
import Label from '@/components/ui/Label.vue'
import Button from '@/components/ui/Button.vue'

const route = useRoute()
const router = useRouter()
const articlesStore = useArticlesStore()

const projectId = computed(() => Number(route.params.id))

const statusFilter = ref<ArticleStatus | ''>('')
const decisionFilter = ref<FinalDecision | ''>('')
const currentPage = ref(1)

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'imported', label: 'Imported' },
  { value: 'screening', label: 'Screening' },
  { value: 'awaiting_full_text', label: 'Awaiting Full Text' },
  { value: 'full_text_retrieved', label: 'Full Text Retrieved' },
  { value: 'included', label: 'Included' },
  { value: 'excluded', label: 'Excluded' },
]

const decisionOptions = [
  { value: '', label: 'All Decisions' },
  { value: 'pending', label: 'Pending' },
  { value: 'included', label: 'Included' },
  { value: 'excluded', label: 'Excluded' },
]

const fetchArticles = () => {
  articlesStore.fetchArticles(projectId.value, {
    status: statusFilter.value || undefined,
    final_decision: decisionFilter.value || undefined,
    page: currentPage.value,
  })
}

onMounted(() => {
  fetchArticles()
})

watch([statusFilter, decisionFilter], () => {
  currentPage.value = 1
  fetchArticles()
})

const goToArticle = (articleId: number) => {
  router.push({
    name: 'article-detail',
    params: { id: projectId.value, articleId },
  })
}

const nextPage = () => {
  if (currentPage.value < articlesStore.pagination.pages) {
    currentPage.value++
    fetchArticles()
  }
}

const previousPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--
    fetchArticles()
  }
}

const getStatusBadgeVariant = (status: ArticleStatus) => {
  const variants: Record<ArticleStatus, 'default' | 'secondary' | 'outline'> = {
    imported: 'outline',
    screening: 'default',
    awaiting_full_text: 'secondary',
    full_text_retrieved: 'default',
    included: 'default',
    excluded: 'secondary',
  }
  return variants[status] || 'outline'
}

const getDecisionBadgeVariant = (decision: FinalDecision) => {
  const variants: Record<FinalDecision, 'default' | 'secondary' | 'outline'> = {
    pending: 'outline',
    included: 'default',
    excluded: 'destructive',
  }
  return variants[decision] || 'outline'
}
</script>

<template>
  <div class="space-y-6">
    <!-- Filters -->
    <Card class="p-4">
      <div class="grid gap-4 md:grid-cols-3">
        <div class="space-y-2">
          <Label>Status</Label>
          <Select v-model="statusFilter" :options="statusOptions" />
        </div>

        <div class="space-y-2">
          <Label>Decision</Label>
          <Select v-model="decisionFilter" :options="decisionOptions" />
        </div>

        <div class="flex items-end">
          <Button
            variant="outline"
            @click="() => { statusFilter = ''; decisionFilter = '' }"
          >
            Clear Filters
          </Button>
        </div>
      </div>
    </Card>

    <!-- Articles List -->
    <div v-if="articlesStore.loading" class="text-center py-12">
      <p class="text-muted-foreground">Loading articles...</p>
    </div>

    <div v-else-if="articlesStore.articles?.length === 0" class="text-center py-12">
      <p class="text-muted-foreground">No articles found</p>
    </div>

    <div v-else class="space-y-4">
      <Card
        v-for="article in articlesStore.articles"
        :key="article.id"
        class="p-4 cursor-pointer hover:shadow-lg transition-shadow"
        @click="goToArticle(article.id)"
      >
        <div class="space-y-3">
          <div class="flex items-start justify-between gap-4">
            <h3 class="text-lg font-semibold flex-1">
              {{ article.title || 'Untitled' }}
            </h3>
            <div class="flex gap-2 flex-shrink-0">
              <Badge :variant="getStatusBadgeVariant(article.status)">
                {{ article.status }}
              </Badge>
              <Badge :variant="getDecisionBadgeVariant(article.final_decision)">
                {{ article.final_decision }}
              </Badge>
            </div>
          </div>

          <div class="text-sm text-muted-foreground">
            <p v-if="article.authors.length > 0">
              {{ article.authors.slice(0, 3).join(', ') }}
              <span v-if="article.authors.length > 3">et al.</span>
            </p>
            <p v-if="article.year || article.journal">
              <span v-if="article.year">{{ article.year }}</span>
              <span v-if="article.year && article.journal"> - </span>
              <span v-if="article.journal">{{ article.journal }}</span>
            </p>
          </div>

          <p v-if="article.abstract" class="text-sm text-muted-foreground line-clamp-2">
            {{ article.abstract }}
          </p>
        </div>
      </Card>
    </div>

    <!-- Pagination -->
    <div v-if="articlesStore.pagination.pages > 1" class="flex items-center justify-between">
      <p class="text-sm text-muted-foreground">
        Page {{ currentPage }} of {{ articlesStore.pagination.pages }}
        ({{ articlesStore.pagination.total }} total)
      </p>

      <div class="flex gap-2">
        <Button
          variant="outline"
          @click="previousPage"
          :disabled="currentPage === 1"
        >
          Previous
        </Button>
        <Button
          variant="outline"
          @click="nextPage"
          :disabled="currentPage === articlesStore.pagination.pages"
        >
          Next
        </Button>
      </div>
    </div>
  </div>
</template>
