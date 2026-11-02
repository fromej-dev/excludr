<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useStoppingRuleStore } from '@/stores/stoppingRule'
import { useWebSocketStore } from '@/stores/websocket'
import type { ApplyStoppingRuleResult } from '@/types'
import Dialog from '@/components/ui/Dialog.vue'
import Button from '@/components/ui/Button.vue'
import Label from '@/components/ui/Label.vue'
import Textarea from '@/components/ui/Textarea.vue'

interface Props {
  projectId: number
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  applied: [result: ApplyStoppingRuleResult]
}>()

const store = useStoppingRuleStore()
const wsStore = useWebSocketStore()

const reason = ref('')
const submitting = ref(false)
const errorText = ref<string | null>(null)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    reason.value = ''
    errorText.value = null
    void store.fetch(props.projectId)
  },
  { immediate: true }
)

const s = computed(() => store.status)
const forced = computed(() => !!s.value && !s.value.met)
const leftOpen = computed(() => (s.value ? Math.max(0, s.value.remaining - s.value.closable) : 0))
const canSubmit = computed(
  () =>
    !!s.value &&
    !store.loading &&
    s.value.enabled &&
    s.value.closable > 0 &&
    !submitting.value &&
    (!forced.value || reason.value.trim().length > 0)
)

const submit = async () => {
  if (!s.value || !canSubmit.value) return
  submitting.value = true
  errorText.value = null
  const outcome = await store.apply(props.projectId, {
    force: forced.value,
    reason: forced.value ? reason.value.trim() : undefined,
  })
  submitting.value = false
  if (outcome.ok) {
    emit('applied', outcome.result)
    emit('update:open', false)
    wsStore.addNotification(`Stopping rule applied: ${outcome.result.closed} records closed`, 'info')
    if (outcome.result.not_started > 0) {
      wsStore.addNotification(
        `${outcome.result.not_started} imported records were not released for screening and stay untouched.`,
        'info'
      )
    }
    return
  }
  errorText.value =
    outcome.status === 402 ? `${outcome.message}. This review's pass has expired.` : outcome.message
  // A race (e.g. the streak was reset): show the real state, which may switch to the forced path
  if (outcome.status === 409) await store.fetch(props.projectId)
}
</script>

<template>
  <Dialog :open="open" title="Apply stopping rule" @update:open="emit('update:open', $event)">
    <div class="space-y-3 text-sm" data-testid="apply-rule-dialog">
      <p v-if="!s" class="text-muted-foreground">
        {{ store.error ?? 'Loading…' }}
      </p>
      <template v-else>
        <p v-if="!s.enabled" class="text-muted-foreground">
          Set a stopping threshold in Screening settings first.
        </p>
        <template v-else>
          <p v-if="s.met">
            {{ s.consecutive_excludes }} consecutive excludes (rule: {{ s.threshold }}).
          </p>
          <div
            v-else
            class="rounded-md border border-uncertain/60 bg-uncertain-soft p-3 text-uncertain-soft-foreground"
            data-testid="apply-rule-not-met"
          >
            The rule is not met yet: {{ s.consecutive_excludes }} of {{ s.threshold }} consecutive
            excludes. Closing records now must be justified in your report.
          </div>

          <div v-if="forced" class="space-y-1.5">
            <Label for="apply-rule-reason">Reason (recorded in the audit log and the methods text)</Label>
            <Textarea
              id="apply-rule-reason"
              v-model="reason"
              maxlength="2000"
              data-testid="apply-rule-reason"
            />
          </div>

          <p v-if="s.closable === 0" data-testid="apply-rule-nothing">
            Nothing to close: every remaining record has a reviewer decision.
          </p>
          <ul v-else class="list-disc space-y-1 pl-5">
            <li data-testid="apply-rule-closable">
              <strong>{{ s.closable }}</strong> records with no reviewer decision will be closed as
              <em>Not screened (stopping rule)</em>.
            </li>
            <li v-if="leftOpen > 0" data-testid="apply-rule-left-open">
              <strong>{{ leftOpen }}</strong> records a reviewer has started (partly reviewed, uncertain
              or in conflict) stay open.
            </li>
            <li v-if="s.not_screened > 0">{{ s.not_screened }} records were already closed earlier.</li>
          </ul>
          <p class="text-xs text-muted-foreground">
            They are not counted as exclusions and are reported in PRISMA as <em>marked as
            ineligible by automation tools</em>. You can reopen them from Articles.
          </p>
        </template>
      </template>

      <p v-if="errorText" role="alert" class="text-destructive" data-testid="apply-rule-error">
        {{ errorText }}
      </p>

      <div class="flex justify-end gap-2 pt-2">
        <Button variant="outline" @click="emit('update:open', false)">Cancel</Button>
        <Button
          variant="destructive"
          :disabled="!canSubmit"
          data-testid="apply-rule-confirm"
          @click="submit"
        >
          Close {{ s?.closable ?? 0 }} records{{ forced ? ' anyway' : '' }}
        </Button>
      </div>
    </div>
  </Dialog>
</template>
