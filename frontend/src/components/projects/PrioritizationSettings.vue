<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import { useStoppingRuleStore, refreshAfterRuleChange } from '@/stores/stoppingRule'
import { useWebSocketStore } from '@/stores/websocket'
import type { Project, ProjectUpdate, RankingRun } from '@/types'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import ApplyStoppingRuleDialog from '@/components/screening/ApplyStoppingRuleDialog.vue'
import { formatDate } from '@/utils/format'

interface Props {
  project: Project
  canEdit: boolean
  readOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), { readOnly: false })

const projectsStore = useProjectsStore()
const ruleStore = useStoppingRuleStore()
const wsStore = useWebSocketStore()

const DEFAULT_THRESHOLD = 100
const THRESHOLD_MAX = 100000
const RANDOM_MAX = 10000

const editable = computed(() => props.canEdit && !props.readOnly)
const prioritized = computed(() => props.project.prioritized_screening)

// ---- Toggle (saves immediately) ----
const toggling = ref(false)
const onToggle = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const next = input.checked
  toggling.value = true
  const updated = await projectsStore.updateProject(props.project.id, { prioritized_screening: next })
  toggling.value = false
  if (updated) {
    wsStore.addNotification(`Prioritized screening ${next ? 'on' : 'off'}`, 'success')
    if (next) void ruleStore.fetch(props.project.id)
  } else {
    input.checked = props.project.prioritized_screening
    wsStore.addNotification(projectsStore.error ?? 'Failed to update setting', 'error')
  }
}

// ---- Rule form ----
const ruleOn = ref(props.project.stop_after_consecutive_excludes !== null)
const threshold = ref(String(props.project.stop_after_consecutive_excludes ?? DEFAULT_THRESHOLD))
const minRandom = ref(String(props.project.ranking_min_random))
const touched = ref(false)
const saving = ref(false)

const syncForm = () => {
  ruleOn.value = props.project.stop_after_consecutive_excludes !== null
  threshold.value = String(props.project.stop_after_consecutive_excludes ?? DEFAULT_THRESHOLD)
  minRandom.value = String(props.project.ranking_min_random)
  touched.value = false
}

// Follow the project, but never overwrite unsaved edits
watch(
  () => [props.project.stop_after_consecutive_excludes, props.project.ranking_min_random] as const,
  () => {
    if (!touched.value) syncForm()
  }
)

const parseInteger = (text: string): number | null => {
  const t = text.trim()
  return /^\d+$/.test(t) ? Number(t) : null
}

const thresholdError = computed(() => {
  if (!ruleOn.value) return null
  const n = parseInteger(threshold.value)
  return n === null || n < 1 || n > THRESHOLD_MAX ? `Enter a whole number from 1 to ${THRESHOLD_MAX}` : null
})
const randomError = computed(() => {
  const n = parseInteger(minRandom.value)
  return n === null || n > RANDOM_MAX ? `Enter a whole number from 0 to ${RANDOM_MAX}` : null
})

/** Only the keys that differ from the saved project. */
const changes = computed<ProjectUpdate>(() => {
  const patch: ProjectUpdate = {}
  const saved = props.project.stop_after_consecutive_excludes
  if (!ruleOn.value) {
    if (saved !== null) patch.stop_after_consecutive_excludes = null
  } else {
    const n = parseInteger(threshold.value)
    if (n !== null && n !== saved) patch.stop_after_consecutive_excludes = n
  }
  const r = parseInteger(minRandom.value)
  if (r !== null && r !== props.project.ranking_min_random) patch.ranking_min_random = r
  return patch
})
const canSave = computed(
  () =>
    editable.value &&
    !saving.value &&
    !thresholdError.value &&
    !randomError.value &&
    Object.keys(changes.value).length > 0
)

const save = async () => {
  if (!canSave.value) return
  saving.value = true
  const updated = await projectsStore.updateProject(props.project.id, changes.value)
  saving.value = false
  if (updated) {
    touched.value = false
    syncForm()
    wsStore.addNotification('Screening rule saved', 'success')
    void ruleStore.fetch(props.project.id)
  } else {
    wsStore.addNotification(projectsStore.error ?? 'Failed to save the screening rule', 'error')
  }
}

// ---- Status panel ----
const status = computed(() => (ruleStore.projectId === props.project.id ? ruleStore.status : null))
const loadStatus = () => ruleStore.fetch(props.project.id)

onMounted(() => {
  if (prioritized.value) void loadStatus()
})
watch(prioritized, (on) => {
  if (on) void loadStatus()
})

const METHOD_LABELS: Record<RankingRun['method'], string> = {
  model: 'relevance model',
  similarity: 'cold start (text similarity to the review question and criteria)',
  random: 'cold start (random order)',
}

const lastRun = computed(() => status.value?.last_run ?? null)

// ---- Owner actions ----
const rerank = async () => {
  const res = await ruleStore.rerank(props.project.id)
  if (!res) {
    wsStore.addNotification(ruleStore.error ?? 'Failed to start re-ranking', 'error')
  } else if (res.status === 'queued') {
    wsStore.addNotification('A ranking is running; yours follows it', 'info')
  }
}

const applyOpen = ref(false)
const onApplied = () => void refreshAfterRuleChange(props.project.id)
</script>

<template>
  <div class="space-y-4" data-testid="prioritization-settings">
    <div class="space-y-1.5">
      <div class="flex items-start gap-2">
        <input
          id="prioritized-screening"
          type="checkbox"
          class="mt-1 h-4 w-4 accent-primary"
          data-testid="prioritized-toggle"
          :checked="prioritized"
          :disabled="!editable || toggling"
          @change="onToggle"
        />
        <div>
          <Label for="prioritized-screening">Prioritize title/abstract screening by predicted relevance</Label>
          <p class="text-xs text-muted-foreground">
            Records most likely to be relevant come first. A model is retrained on your reviewers'
            title/abstract decisions; AI verdicts are never used, and it costs nothing.
          </p>
        </div>
      </div>
      <p v-if="!canEdit" class="text-xs text-muted-foreground">Only the owner can change this.</p>
      <p v-else-if="readOnly" class="text-xs text-muted-foreground">
        This review's pass has expired; settings are read-only.
      </p>
    </div>

    <form v-if="prioritized" class="space-y-4 pl-6" @submit.prevent="save">
      <div class="space-y-2">
        <div class="flex items-center gap-2">
          <input
            id="stopping-rule-on"
            v-model="ruleOn"
            type="checkbox"
            class="h-4 w-4 accent-primary"
            data-testid="stopping-rule-toggle"
            :disabled="!editable"
            @change="touched = true"
          />
          <Label for="stopping-rule-on">Use a stopping rule</Label>
        </div>
        <div class="max-w-xs space-y-1.5">
          <Label for="stop-threshold">Stop after this many consecutive excludes</Label>
          <Input
            id="stop-threshold"
            v-model="threshold"
            type="number"
            min="1"
            :max="THRESHOLD_MAX"
            step="1"
            data-testid="stop-threshold"
            :disabled="!editable || !ruleOn"
            @update:model-value="touched = true"
          />
          <p v-if="thresholdError" role="alert" class="text-xs text-destructive">{{ thresholdError }}</p>
        </div>
      </div>

      <div class="max-w-xs space-y-1.5">
        <Label for="ranking-min-random">Random start: show the first N records in random order</Label>
        <Input
          id="ranking-min-random"
          v-model="minRandom"
          type="number"
          min="0"
          :max="RANDOM_MAX"
          step="1"
          data-testid="ranking-min-random"
          :disabled="!editable"
          @update:model-value="touched = true"
        />
        <p class="text-xs text-muted-foreground">
          0 = rank from the start. A random start gives the model an unbiased first sample.
        </p>
        <p v-if="randomError" role="alert" class="text-xs text-destructive">{{ randomError }}</p>
      </div>

      <p class="flex gap-2 text-xs text-muted-foreground" data-testid="protocol-note">
        <span aria-hidden="true">ⓘ</span>
        <span>
          State the stopping rule in your review protocol before you start. Records it closes are never
          excluded by a reviewer: they are reported as <em>marked as ineligible by automation tools</em>
          in PRISMA, listed as <em>Not screened (stopping rule)</em> in exports, and can be reopened.
        </span>
      </p>

      <Button v-if="canEdit" type="submit" size="sm" :disabled="!canSave" data-testid="prioritization-save">
        Save
      </Button>
    </form>

    <div v-if="prioritized" class="space-y-2 border-t pt-3 text-sm" data-testid="ranking-status">
      <div v-if="!status && ruleStore.loading" class="space-y-2" aria-busy="true">
        <div v-for="n in 3" :key="n" class="h-4 animate-pulse rounded bg-muted" />
      </div>
      <p v-else-if="!status" class="text-muted-foreground">
        Couldn't load ranking status
        <button type="button" class="ml-1 font-medium text-primary hover:underline" @click="loadStatus">
          Retry
        </button>
      </p>
      <template v-else>
        <p data-testid="ranking-last-run">
          <template v-if="lastRun">
            Last ranked {{ formatDate(lastRun.created_at) }} · {{ METHOD_LABELS[lastRun.method] }} ·
            trained on {{ lastRun.labelled_includes }} includes and {{ lastRun.labelled_excludes }}
            excludes · {{ lastRun.scored }} records scored
            <span v-if="lastRun.method !== 'model'" class="block text-xs text-muted-foreground">
              The model starts once at least one record has been included and one excluded at
              title/abstract.
            </span>
          </template>
          <template v-else>Not ranked yet.</template>
        </p>
        <p v-if="status.enabled" data-testid="rule-status" class="flex flex-wrap items-center gap-2">
          <span>
            {{ status.consecutive_excludes }} / {{ status.threshold }} consecutive excludes ·
            {{ status.screened }} screened · {{ status.remaining }} still at title/abstract
            ({{ status.closable }} not started by a reviewer)
          </span>
          <Badge v-if="status.met" variant="ai">Rule met</Badge>
        </p>
        <p v-if="status.applied_at" data-testid="rule-applied">
          Applied {{ formatDate(status.applied_at) }}: {{ status.not_screened }} records not screened
          <router-link
            :to="{ name: 'project-articles', params: { id: project.id }, query: { status: 'not_screened' } }"
            class="ml-1 font-medium text-primary hover:underline"
          >
            View
          </router-link>
        </p>
      </template>

      <div v-if="canEdit && !readOnly" class="flex flex-wrap gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          :disabled="ruleStore.reranking"
          data-testid="rerank-button"
          @click="rerank"
        >
          {{ ruleStore.reranking ? 'Re-ranking…' : 'Re-rank now' }}
        </Button>
        <Button
          variant="outline"
          size="sm"
          :disabled="!status || !status.enabled || status.closable <= 0"
          data-testid="apply-rule-open"
          @click="applyOpen = true"
        >
          Apply stopping rule…
        </Button>
      </div>
    </div>

    <ApplyStoppingRuleDialog v-model:open="applyOpen" :project-id="project.id" @applied="onApplied" />
  </div>
</template>
