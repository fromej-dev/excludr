<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useConflictsStore } from '@/stores/conflicts'
import { useMembersStore } from '@/stores/members'
import { useWebSocketStore } from '@/stores/websocket'
import type { Conflict, ScreeningDecisionType, ResolveRequest } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Dialog from '@/components/ui/Dialog.vue'

const route = useRoute()
const conflictsStore = useConflictsStore()
const membersStore = useMembersStore()
const wsStore = useWebSocketStore()

const projectId = computed(() => Number(route.params.id))
const isOwner = computed(() => membersStore.isOwner)

const target = ref<Conflict | null>(null)
const choice = ref<ResolveRequest['decision']>('include')
const reason = ref('')
const exclusionReason = ref('')
const submitting = ref(false)
const formError = ref<string | null>(null)

onMounted(() => {
  if (isOwner.value) conflictsStore.fetchConflicts(projectId.value)
})

// The role arrives asynchronously after a page reload
watch(isOwner, (owner, was) => {
  if (owner && !was) conflictsStore.fetchConflicts(projectId.value)
})

const openResolve = (c: Conflict) => {
  target.value = c
  choice.value = 'include'
  reason.value = ''
  exclusionReason.value = ''
  formError.value = null
}

const submit = async () => {
  if (!target.value || !reason.value.trim()) return
  submitting.value = true
  formError.value = null
  const err = await conflictsStore.resolve(projectId.value, target.value.article_id, {
    decision: choice.value,
    reason: reason.value.trim(),
    primary_exclusion_reason:
      choice.value === 'exclude' && exclusionReason.value.trim() ? exclusionReason.value.trim() : undefined,
  })
  submitting.value = false
  if (err) {
    formError.value = err
  } else {
    wsStore.addNotification('Conflict resolved', 'success')
    target.value = null
  }
}

const variant = (d: ScreeningDecisionType) =>
  d === 'include' ? 'default' : d === 'exclude' ? 'destructive' : 'outline'
</script>

<template>
  <div class="space-y-4">
    <Card v-if="!isOwner" class="p-6 text-sm text-muted-foreground">
      Only the project owner can view and resolve conflicts.
    </Card>

    <template v-else>
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold">Reviewer conflicts</h2>
          <p class="text-sm text-muted-foreground">
            Articles where reviewers disagree. Your resolution becomes the final decision.
          </p>
        </div>
        <Badge variant="secondary">{{ conflictsStore.conflicts.length }} open</Badge>
      </div>

      <p v-if="conflictsStore.error" class="text-sm text-destructive" role="alert">{{ conflictsStore.error }}</p>
      <p v-else-if="conflictsStore.loading" class="text-sm text-muted-foreground">Loading conflicts...</p>

      <Card v-else-if="conflictsStore.conflicts.length === 0" class="p-12 text-center">
        <h3 class="text-lg font-semibold">No conflicts</h3>
        <p class="text-sm text-muted-foreground mt-1">All reviewer decisions agree.</p>
      </Card>

      <Card
        v-for="c in conflictsStore.conflicts"
        :key="c.article_id"
        class="p-4 space-y-3"
        data-testid="conflict-card"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <router-link
              :to="{ name: 'article-detail', params: { id: projectId, articleId: c.article_id } }"
              class="font-medium hover:underline"
            >
              {{ c.title || 'Untitled' }}
            </router-link>
            <div class="mt-1"><Badge variant="outline">{{ c.stage }}</Badge></div>
          </div>
          <Button size="sm" @click="openResolve(c)">Resolve</Button>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <div v-for="d in c.decisions" :key="d.decision_id" class="rounded-md border p-3 space-y-1">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-medium">{{ d.reviewer_name || 'Unknown reviewer' }}</span>
              <Badge :variant="variant(d.decision)" class="capitalize">{{ d.decision }}</Badge>
            </div>
            <p v-if="d.reasoning" class="text-sm text-muted-foreground">{{ d.reasoning }}</p>
            <p v-if="d.primary_exclusion_reason" class="text-xs text-muted-foreground">
              Exclusion reason: {{ d.primary_exclusion_reason }}
            </p>
          </div>
        </div>
      </Card>
    </template>

    <Dialog :open="target !== null" title="Resolve conflict" @update:open="(v) => !v && (target = null)">
      <form class="space-y-4" @submit.prevent="submit">
        <p class="text-sm text-muted-foreground">{{ target?.title || 'Untitled' }}</p>

        <div class="space-y-2">
          <Label>Final decision</Label>
          <div class="flex gap-2" role="radiogroup" aria-label="Final decision">
            <Button
              type="button"
              role="radio"
              :aria-checked="choice === 'include'"
              :variant="choice === 'include' ? 'default' : 'outline'"
              @click="choice = 'include'"
            >
              Include
            </Button>
            <Button
              type="button"
              role="radio"
              :aria-checked="choice === 'exclude'"
              :variant="choice === 'exclude' ? 'destructive' : 'outline'"
              @click="choice = 'exclude'"
            >
              Exclude
            </Button>
          </div>
        </div>

        <div class="space-y-2">
          <Label for="resolve-reason">Reason (required)</Label>
          <Textarea id="resolve-reason" v-model="reason" :rows="3" placeholder="Why this decision?" />
        </div>

        <div v-if="choice === 'exclude'" class="space-y-2">
          <Label for="resolve-exclusion">Primary exclusion reason (optional)</Label>
          <Input id="resolve-exclusion" v-model="exclusionReason" placeholder="e.g. E1: wrong population" />
        </div>

        <p v-if="formError" class="text-sm text-destructive" role="alert">{{ formError }}</p>

        <div class="flex justify-end gap-3">
          <Button type="button" variant="outline" @click="target = null">Cancel</Button>
          <Button type="submit" :disabled="submitting || !reason.trim()">
            {{ submitting ? 'Saving...' : 'Resolve' }}
          </Button>
        </div>
      </form>
    </Dialog>
  </div>
</template>
