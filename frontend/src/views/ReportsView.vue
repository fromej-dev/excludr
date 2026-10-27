<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useReportsStore } from '@/stores/reports'
import { useMembersStore } from '@/stores/members'
import { useWebSocketStore } from '@/stores/websocket'
import type { ExportFormat, ScreeningDecisionType } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Label from '@/components/ui/Label.vue'
import Select from '@/components/ui/Select.vue'
import PrismaDiagram from '@/components/reports/PrismaDiagram.vue'
import AgreementStats from '@/components/reports/AgreementStats.vue'

const route = useRoute()
const reportsStore = useReportsStore()
const membersStore = useMembersStore()
const wsStore = useWebSocketStore()

const projectId = computed(() => Number(route.params.id))
const isOwner = computed(() => membersStore.isOwner)

type ReportStage = 'title_abstract' | 'full_text'
const stage = ref<ReportStage>('title_abstract')
const stageOptions = [
  { value: 'title_abstract', label: 'Title / abstract' },
  { value: 'full_text', label: 'Full text' },
]

const reload = () => reportsStore.load(projectId.value, stage.value, isOwner.value)

onMounted(reload)
// The role arrives asynchronously (members request); load owner-only data once known
watch(isOwner, (owner, was) => {
  if (owner && !was) reload()
})
watch(stage, (s) => {
  if (!isOwner.value) return
  reportsStore.fetchAgreement(projectId.value, s)
  reportsStore.fetchDisagreements(projectId.value, s)
})

const onExport = async (format: ExportFormat) => {
  const name = await reportsStore.exportArticles(projectId.value, format)
  if (name) wsStore.addNotification(`Downloaded ${name}`, 'success')
  else wsStore.addNotification(reportsStore.error ?? 'Export failed', 'error')
}

const variant = (d: ScreeningDecisionType) =>
  d === 'include' ? 'default' : d === 'exclude' ? 'destructive' : 'outline'
</script>

<template>
  <div class="space-y-6">
    <p v-if="reportsStore.error" class="text-sm text-destructive" role="alert">{{ reportsStore.error }}</p>

    <Card class="p-6 space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold">PRISMA flow</h2>
          <p class="text-sm text-muted-foreground">PRISMA 2020 counts for this review.</p>
        </div>
        <div v-if="isOwner" class="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            :disabled="reportsStore.exporting !== null"
            data-testid="export-csv"
            @click="onExport('csv')"
          >
            {{ reportsStore.exporting === 'csv' ? 'Exporting...' : 'Export CSV' }}
          </Button>
          <Button
            variant="outline"
            size="sm"
            :disabled="reportsStore.exporting !== null"
            data-testid="export-ris"
            @click="onExport('ris')"
          >
            {{ reportsStore.exporting === 'ris' ? 'Exporting...' : 'Export RIS' }}
          </Button>
        </div>
      </div>
      <PrismaDiagram v-if="reportsStore.prisma" :flow="reportsStore.prisma" />
      <p v-else class="text-sm text-muted-foreground">Loading...</p>
    </Card>

    <template v-if="isOwner">
      <Card class="p-6 space-y-4">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Agreement</h2>
            <p class="text-sm text-muted-foreground">Inter-reviewer and AI-vs-human statistics.</p>
          </div>
          <div class="w-48 space-y-1">
            <Label for="report-stage">Stage</Label>
            <Select
              id="report-stage"
              :model-value="stage"
              :options="stageOptions"
              @update:model-value="stage = $event === 'full_text' ? 'full_text' : 'title_abstract'"
            />
          </div>
        </div>
        <AgreementStats v-if="reportsStore.agreement" :agreement="reportsStore.agreement" />
      </Card>

      <Card class="p-6 space-y-4">
        <div>
          <h2 class="text-lg font-semibold">AI disagreements</h2>
          <p class="text-sm text-muted-foreground">
            Articles where the AI's include/exclude differs from the human outcome.
          </p>
        </div>
        <p v-if="reportsStore.disagreements.length === 0" class="text-sm text-muted-foreground">
          No disagreements at this stage.
        </p>
        <ul v-else class="divide-y rounded-md border" data-testid="disagreement-list">
          <li v-for="d in reportsStore.disagreements" :key="d.article_id" class="p-3 space-y-2">
            <router-link
              :to="{ name: 'article-detail', params: { id: projectId, articleId: d.article_id } }"
              class="font-medium hover:underline"
            >
              {{ d.title || 'Untitled' }}
            </router-link>
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span class="text-muted-foreground">AI:</span>
              <Badge :variant="variant(d.ai.decision)" class="capitalize">{{ d.ai.decision }}</Badge>
              <span v-if="d.ai.confidence_score !== null" class="text-xs text-muted-foreground">
                {{ Math.round(d.ai.confidence_score * 100) }}%
              </span>
              <span class="text-muted-foreground ml-2">Human{{ d.human_is_resolution ? ' (resolution)' : '' }}:</span>
              <Badge :variant="variant(d.human_decision)" class="capitalize">{{ d.human_decision }}</Badge>
            </div>
            <p v-if="d.ai.reasoning" class="text-sm text-muted-foreground">{{ d.ai.reasoning }}</p>
          </li>
        </ul>
      </Card>
    </template>
    <Card v-else class="p-4 text-sm text-muted-foreground">
      Agreement statistics, AI disagreements and exports are available to the project owner.
    </Card>
  </div>
</template>
