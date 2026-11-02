<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import { useStoppingRuleStore, refreshAfterRuleChange } from '@/stores/stoppingRule'
import { useWebSocketStore } from '@/stores/websocket'
import type { Project, ProjectUpdate, RankingRun, StoppingRuleType } from '@/types'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import ApplyStoppingRuleDialog from '@/components/screening/ApplyStoppingRuleDialog.vue'
import { formatDate, formatP, formatPercent } from '@/utils/format'

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
const DOI_URL = 'https://doi.org/10.1186/s13643-020-01521-4'
const toPercent = (fraction: number) => String(Math.round(fraction * 10000) / 100)
const isRuleOn = (p: Project) => p.stopping_rule_type === 'statistical' || p.stop_after_consecutive_excludes !== null

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
const ruleOn = ref(isRuleOn(props.project))
const ruleType = ref<StoppingRuleType>(props.project.stopping_rule_type ?? 'consecutive')
const recallPercent = ref(toPercent(props.project.recall_target ?? 0.95))
const alpha = ref(String(props.project.stopping_alpha ?? 0.05))
const threshold = ref(String(props.project.stop_after_consecutive_excludes ?? DEFAULT_THRESHOLD))
const minRandom = ref(String(props.project.ranking_min_random))
const touched = ref(false)
const saving = ref(false)

const syncForm = () => {
  ruleOn.value = isRuleOn(props.project)
  ruleType.value = props.project.stopping_rule_type ?? 'consecutive'
  recallPercent.value = toPercent(props.project.recall_target ?? 0.95)
  alpha.value = String(props.project.stopping_alpha ?? 0.05)
  threshold.value = String(props.project.stop_after_consecutive_excludes ?? DEFAULT_THRESHOLD)
  minRandom.value = String(props.project.ranking_min_random)
  touched.value = false
}

// Follow the project, but never overwrite unsaved edits
watch(
  () =>
    [
      props.project.stop_after_consecutive_excludes,
      props.project.ranking_min_random,
      props.project.stopping_rule_type,
      props.project.recall_target,
      props.project.stopping_alpha,
    ] as const,
  () => {
    if (!touched.value) syncForm()
  }
)

const parseInteger = (text: string): number | null => {
  const t = text.trim()
  return /^\d+$/.test(t) ? Number(t) : null
}

const consecutiveOn = computed(() => ruleOn.value && ruleType.value === 'consecutive')
const statisticalOn = computed(() => ruleOn.value && ruleType.value === 'statistical')

const recallError = computed(() => {
  if (!statisticalOn.value) return null
  const t = recallPercent.value.trim()
  const n = /^\d+(\.\d+)?$/.test(t) ? Number(t) : NaN
  return Number.isFinite(n) && n >= 80 && n <= 99 ? null : 'Enter a percentage from 80 to 99'
})
const alphaError = computed(() => {
  if (!statisticalOn.value) return null
  const t = alpha.value.trim()
  const n = /^\d*\.?\d+$/.test(t) ? Number(t) : NaN
  return Number.isFinite(n) && n >= 0.001 && n <= 0.2 ? null : 'Enter a number from 0.001 to 0.2'
})

const thresholdError = computed(() => {
  if (!consecutiveOn.value) return null
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
  const savedType = props.project.stopping_rule_type ?? 'consecutive'
  if (!ruleOn.value) {
    if (saved !== null) patch.stop_after_consecutive_excludes = null
    if (savedType !== 'consecutive') patch.stopping_rule_type = 'consecutive'
  } else if (ruleType.value === 'statistical') {
    if (savedType !== 'statistical') patch.stopping_rule_type = 'statistical'
    const target = Math.round(Number(recallPercent.value) * 100) / 10000
    if (!recallError.value && target !== props.project.recall_target) patch.recall_target = target
    const a = Number(alpha.value)
    if (!alphaError.value && a !== props.project.stopping_alpha) patch.stopping_alpha = Math.round(a * 10000) / 10000
  } else {
    if (savedType !== 'consecutive') patch.stopping_rule_type = 'consecutive'
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
    !recallError.value &&
    !alphaError.value &&
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
        <fieldset v-if="ruleOn" class="space-y-2" data-testid="stopping-rule-type">
          <legend class="sr-only">Stopping rule type</legend>
          <label class="flex items-start gap-2 text-sm">
            <input
              v-model="ruleType"
              type="radio"
              value="consecutive"
              class="mt-1 h-4 w-4 accent-primary"
              data-testid="rule-type-consecutive"
              :disabled="!editable"
              @change="touched = true"
            />
            <span>Fixed: stop after N consecutive excludes</span>
          </label>
          <label class="flex items-start gap-2 text-sm">
            <input
              v-model="ruleType"
              type="radio"
              value="statistical"
              class="mt-1 h-4 w-4 accent-primary"
              data-testid="rule-type-statistical"
              :disabled="!editable"
              @change="touched = true"
            />
            <span>Statistical: stop when a recall target is shown (Callaghan &amp; Müller-Hansen, 2020)</span>
          </label>
        </fieldset>
        <div v-if="ruleType === 'consecutive' || !ruleOn" class="max-w-xs space-y-1.5">
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
        <div v-else class="space-y-2" data-testid="statistical-fields">
          <div class="flex flex-wrap gap-4">
            <div class="w-40 space-y-1.5">
              <Label for="recall-target">Recall target (%)</Label>
              <Input
                id="recall-target"
                v-model="recallPercent"
                type="number"
                min="80"
                max="99"
                step="1"
                data-testid="recall-target"
                :disabled="!editable"
                @update:model-value="touched = true"
              />
              <p v-if="recallError" role="alert" class="text-xs text-destructive">{{ recallError }}</p>
            </div>
            <div class="w-40 space-y-1.5">
              <Label for="stopping-alpha">Significance level (α)</Label>
              <Input
                id="stopping-alpha"
                v-model="alpha"
                type="number"
                min="0.001"
                max="0.2"
                step="0.001"
                data-testid="stopping-alpha"
                :disabled="!editable"
                @update:model-value="touched = true"
              />
              <p v-if="alphaError" role="alert" class="text-xs text-destructive">{{ alphaError }}</p>
            </div>
          </div>
          <p class="text-xs text-muted-foreground" data-testid="statistical-help">
            Stops when the last records screened make it unlikely (p &lt; α) that recall is below the
            target. It needs more screening when few records are included.
            <a :href="DOI_URL" target="_blank" rel="noopener" class="font-medium text-primary hover:underline">
              About the method
            </a>
          </p>
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
          <template v-if="statisticalOn"> State the recall target and significance level in your protocol.</template>
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
            <template v-if="status.rule_type === 'statistical'">
              <span data-testid="rule-status-statistical">
                Recall ≥ {{ formatPercent(status.recall_target ?? 0.95) }}
                {{ status.met ? 'shown' : 'not yet shown' }}
                <template v-if="status.statistical?.p_value != null">
                  ({{ formatP(status.statistical.p_value) }}, needs &lt; {{ status.alpha }})
                </template>
                ·
              </span>
            </template>
            <template v-else>
              {{ status.consecutive_excludes }} / {{ status.threshold }} consecutive excludes ·
            </template>
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
