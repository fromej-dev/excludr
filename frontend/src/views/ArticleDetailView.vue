<script setup lang="ts">
import { onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useArticlesStore } from '@/stores/articles'
import { useScreeningStore } from '@/stores/screening'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import AiDecisionPanel from '@/components/screening/AiDecisionPanel.vue'
import FullTextPanel from '@/components/articles/FullTextPanel.vue'
import { useMembersStore } from '@/stores/members'
import { useAuthStore } from '@/stores/auth'
import type { ScreeningDecision } from '@/types'

const route = useRoute()
const router = useRouter()
const articlesStore = useArticlesStore()
const screeningStore = useScreeningStore()

const projectId = computed(() => Number(route.params.id))
const articleId = computed(() => Number(route.params.articleId))
const membersStore = useMembersStore()
const authStore = useAuthStore()
const article = computed(() => articlesStore.currentArticle)
const isOwner = computed(() => membersStore.isOwner)

// Blinding: the API already hides other reviewers' decisions from non-owners while an
// article is being screened; additionally never show them client-side to non-owners.
const visibleDecisions = computed<ScreeningDecision[]>(() =>
  screeningStore.decisions.filter(
    (d) => isOwner.value || d.source === 'ai_agent' || d.is_resolution || d.reviewer_id === authStore.user?.id
  )
)

const load = () => {
  articlesStore.fetchArticle(projectId.value, articleId.value)
  screeningStore.fetchDecisions(projectId.value, articleId.value)
  screeningStore.fetchAiDecision(projectId.value, articleId.value)
}

onMounted(load)
watch(articleId, load)

const refreshArticle = () => {
  articlesStore.fetchArticle(projectId.value, articleId.value)
}

// Return to the list exactly as the user left it: when the previous history entry is this project's
// articles list (including its filter/sort/page query) step back to it, otherwise (deep link, other
// page) open the plain list.
const goBack = () => {
  const listPath = router.resolve({ name: 'project-articles', params: { id: projectId.value } }).path
  const previous = (window.history.state as { back?: string | null } | null)?.back
  if (previous && previous.split('?')[0] === listPath) {
    router.back()
  } else {
    router.push({ name: 'project-articles', params: { id: projectId.value } })
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-4">
      <Button variant="outline" @click="goBack">
        Back to Articles
      </Button>
    </div>

    <div v-if="article" class="grid gap-4 lg:grid-cols-2 items-start">
    <div class="space-y-4 min-w-0">
    <Card class="p-6">
      <div class="space-y-6">
        <div>
          <div class="flex items-start justify-between gap-4 mb-4">
            <h1 class="text-2xl font-bold flex-1" data-testid="article-detail-title">{{ article.title || 'Untitled' }}</h1>
            <div class="flex gap-2 flex-shrink-0">
              <Badge>{{ article.status }}</Badge>
              <Badge :variant="article.final_decision === 'included' ? 'include' : article.final_decision === 'excluded' ? 'exclude' : 'outline'">{{ article.final_decision }}</Badge>
            </div>
          </div>

          <div v-if="article.authors.length > 0" class="text-muted-foreground mb-2">
            {{ article.authors.join(', ') }}
          </div>

          <div class="flex gap-4 text-sm text-muted-foreground">
            <span v-if="article.year">Year: {{ article.year }}</span>
            <span v-if="article.journal">Journal: {{ article.journal }}</span>
            <span v-if="article.doi">DOI: {{ article.doi }}</span>
            <span v-if="article.pmid">PMID: {{ article.pmid }}</span>
          </div>
        </div>

        <div v-if="article.abstract">
          <h2 class="text-lg font-semibold mb-2">Abstract</h2>
          <p class="text-muted-foreground">{{ article.abstract }}</p>
        </div>

        <div v-if="article.keywords.length > 0">
          <h2 class="text-lg font-semibold mb-2">Keywords</h2>
          <div class="flex flex-wrap gap-2">
            <Badge v-for="keyword in article.keywords" :key="keyword" variant="outline">
              {{ keyword }}
            </Badge>
          </div>
        </div>

      </div>
    </Card>

    <FullTextPanel :article="article" :can-upload="isOwner" @uploaded="refreshArticle" />
    </div>

    <div class="space-y-4 min-w-0">
      <AiDecisionPanel :decision="screeningStore.aiDecision" :loading="screeningStore.aiScreeningLoading" />

      <Card class="p-6">
        <h2 class="text-lg font-semibold mb-4">Screening History</h2>
        <p v-if="visibleDecisions.length === 0" class="text-sm text-muted-foreground">
          No screening decisions yet.
        </p>
        <div v-else>
          <div class="space-y-3">
            <Card
              v-for="decision in visibleDecisions"
              :key="decision.id"
              class="p-4"
            >
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <Badge>{{ decision.stage }}</Badge>
                  <Badge :variant="decision.decision === 'include' ? 'include' : decision.decision === 'exclude' ? 'exclude' : 'uncertain'">
                    {{ decision.decision }}
                  </Badge>
                </div>

                <div v-if="decision.reasoning" class="text-sm">
                  <span class="font-medium">Reasoning:</span> {{ decision.reasoning }}
                </div>

                <div v-if="decision.confidence_score" class="text-sm text-muted-foreground">
                  Confidence: {{ (decision.confidence_score * 100).toFixed(0) }}%
                </div>

                <div class="text-xs text-muted-foreground">
                  {{ new Date(decision.created_at).toLocaleString() }} - {{ decision.source }}
                </div>
              </div>
            </Card>
          </div>
        </div>
      </Card>
    </div>
    </div>

    <div v-if="articlesStore.loading" class="text-center py-12">
      <p class="text-muted-foreground">Loading article...</p>
    </div>
  </div>
</template>
