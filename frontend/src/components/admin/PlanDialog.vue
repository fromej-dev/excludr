<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { useWebSocketStore } from '@/stores/websocket'
import { getErrorMessage } from '@/utils/errors'
import { formatCount, formatDate, toDateInput } from '@/utils/format'
import type { AdminProject } from '@/types'
import Dialog from '@/components/ui/Dialog.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Select from '@/components/ui/Select.vue'

const props = defineProps<{ project: AdminProject | null }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const admin = useAdminStore()
const wsStore = useWebSocketStore()

const DAY_MS = 24 * 60 * 60 * 1000
const tiers = [
  { value: 'pass_250', label: 'Review pass, 250 full texts' },
  { value: 'pass_1000', label: 'Review pass, 1,000 full texts' },
  { value: 'custom', label: 'Custom limit' },
]

const plan = computed(() => props.project?.plan ?? null)
const granting = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)

// Change form
const limit = ref<string | number>('')
const endDate = ref<string | number>('')
// Grant form
const tier = ref<string | number>('pass_250')
const customLimit = ref<string | number>('')
const days = ref<string | number>(365)

watch(
  () => props.project,
  (project) => {
    error.value = null
    granting.value = !project?.plan
    limit.value = project?.plan?.fulltext_limit ?? ''
    endDate.value = project?.plan ? toDateInput(project.plan.expires_at) : ''
    tier.value = 'pass_250'
    customLimit.value = ''
    days.value = 365
  },
  { immediate: true }
)

/** End of the chosen day, UTC. */
const endOfDay = (date: string) => `${date}T23:59:59Z`

const extendBy = (n: number) => {
  if (!plan.value) return
  const from = Math.max(Date.now(), new Date(plan.value.expires_at).getTime())
  endDate.value = new Date(from + n * DAY_MS).toISOString().slice(0, 10)
}

const run = async (action: () => Promise<unknown>, done: string) => {
  saving.value = true
  error.value = null
  try {
    await action()
    wsStore.addNotification(done, 'success')
    emit('saved')
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not save the change')
  } finally {
    saving.value = false
  }
}

const saveChanges = () => {
  if (!props.project || !plan.value) return
  const body: { fulltext_limit?: number; expires_at?: string } = {}
  if (Number(limit.value) !== plan.value.fulltext_limit) body.fulltext_limit = Number(limit.value)
  if (endDate.value && endDate.value !== toDateInput(plan.value.expires_at)) {
    body.expires_at = endOfDay(String(endDate.value))
  }
  if (!Object.keys(body).length) {
    emit('close')
    return
  }
  const id = props.project.id
  void run(() => admin.updatePass(id, body), 'Pass updated')
}

const endNow = () => {
  if (!props.project) return
  if (!window.confirm('End this pass now? The project becomes read-only.')) return
  const id = props.project.id
  void run(() => admin.updatePass(id, { expires_at: new Date().toISOString() }), 'Pass ended')
}

const grant = () => {
  if (!props.project) return
  const id = props.project.id
  const body = {
    tier: String(tier.value),
    days: Number(days.value),
    ...(tier.value === 'custom' ? { fulltext_limit: Number(customLimit.value) } : {}),
  }
  void run(() => admin.grantPass(id, body), 'Pass granted')
}
</script>

<template>
  <Dialog
    :open="project !== null"
    :title="project ? `Plan: ${project.name}` : ''"
    @update:open="(v) => !v && emit('close')"
  >
    <div v-if="project" class="space-y-5" data-testid="plan-dialog">
      <p class="text-sm text-muted-foreground">
        Owner {{ project.owner_email }} · {{ formatCount(project.ai_fulltext_used) }} full texts
        screened by AI
      </p>

      <template v-if="plan && !granting">
        <div class="rounded-md border p-3 text-sm">
          <p>
            <span class="font-medium">{{ plan.tier }}</span>, {{ formatCount(plan.fulltext_limit) }} full
            texts, via {{ plan.source }}
          </p>
          <p class="text-muted-foreground">
            {{ formatDate(plan.activated_at) }} – {{ formatDate(plan.expires_at) }}
          </p>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2">
            <Label for="plan-limit">Full-text limit</Label>
            <Input id="plan-limit" v-model="limit" type="number" />
          </div>
          <div class="space-y-2">
            <Label for="plan-end">Ends on</Label>
            <Input id="plan-end" v-model="endDate" type="date" />
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" @click="extendBy(30)">+30 days</Button>
          <Button size="sm" variant="outline" @click="extendBy(365)">+1 year</Button>
          <Button size="sm" variant="outline" @click="granting = true">Replace with a new pass</Button>
        </div>
      </template>

      <template v-else>
        <p v-if="plan" class="text-sm">
          A new pass starts today and replaces the current one.
        </p>
        <div class="space-y-2">
          <Label for="grant-tier">Pass</Label>
          <Select id="grant-tier" v-model="tier" :options="tiers" />
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-if="tier === 'custom'" class="space-y-2">
            <Label for="grant-limit">Full-text limit</Label>
            <Input id="grant-limit" v-model="customLimit" type="number" required />
          </div>
          <div class="space-y-2">
            <Label for="grant-days">Days</Label>
            <Input id="grant-days" v-model="days" type="number" />
          </div>
        </div>
      </template>

      <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
        {{ error }}
      </p>

      <div class="flex flex-wrap justify-between gap-2">
        <Button
          v-if="plan && plan.active && !granting"
          variant="destructive"
          size="sm"
          :disabled="saving"
          @click="endNow"
        >
          End now
        </Button>
        <span v-else />
        <div class="flex gap-2">
          <Button variant="outline" size="sm" :disabled="saving" @click="plan && granting ? (granting = false) : emit('close')">
            {{ plan && granting ? 'Back' : 'Cancel' }}
          </Button>
          <Button v-if="granting" size="sm" :disabled="saving" data-testid="grant-pass" @click="grant">
            Grant pass
          </Button>
          <Button v-else size="sm" :disabled="saving" data-testid="save-plan" @click="saveChanges">
            Save
          </Button>
        </div>
      </div>
    </div>
  </Dialog>
</template>
