<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useArticlesStore } from '@/stores/articles'
import { useScreeningStore } from '@/stores/screening'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'

const route = useRoute()
const router = useRouter()
const articlesStore = useArticlesStore()
const screeningStore = useScreeningStore()

const projectId = computed(() => Number(route.params.id))
const articleId = computed(() => Number(route.params.articleId))
const article = computed(() => articlesStore.currentArticle)

onMounted(() => {
  articlesStore.fetchArticle(projectId.value, articleId.value)
  screeningStore.fetchDecisions(projectId.value, articleId.value)
})

const goBack = () => {
  router.push({ name: 'project-articles', params: { id: projectId.value } })
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-4">
      <Button variant="outline" @click="goBack">
        Back to Articles
      </Button>
    </div>

    <Card v-if="article" class="p-6">
      <div class="space-y-6">
        <div>
          <div class="flex items-start justify-between gap-4 mb-4">
            <h1 class="text-2xl font-bold flex-1">{{ article.title || 'Untitled' }}</h1>
            <div class="flex gap-2 flex-shrink-0">
              <Badge>{{ article.status }}</Badge>
              <Badge>{{ article.final_decision }}</Badge>
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

        <div v-if="screeningStore.decisions.length > 0">
          <h2 class="text-lg font-semibold mb-4">Screening History</h2>
          <div class="space-y-3">
            <Card
              v-for="decision in screeningStore.decisions"
              :key="decision.id"
              class="p-4"
            >
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <Badge>{{ decision.stage }}</Badge>
                  <Badge :variant="decision.decision === 'include' ? 'default' : decision.decision === 'exclude' ? 'destructive' : 'outline'">
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
      </div>
    </Card>

    <div v-if="articlesStore.loading" class="text-center py-12">
      <p class="text-muted-foreground">Loading article...</p>
    </div>
  </div>
</template>
