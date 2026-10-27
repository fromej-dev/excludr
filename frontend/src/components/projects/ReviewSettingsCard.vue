<script setup lang="ts">
import { ref, watch } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import { useWebSocketStore } from '@/stores/websocket'
import type { Project } from '@/types'
import Card from '@/components/ui/Card.vue'
import Label from '@/components/ui/Label.vue'
import Select from '@/components/ui/Select.vue'

interface Props {
  project: Project
  canEdit: boolean
}

const props = defineProps<Props>()
const projectsStore = useProjectsStore()
const wsStore = useWebSocketStore()

const value = ref<string>(String(props.project.required_reviewers))
const saving = ref(false)

watch(
  () => props.project.required_reviewers,
  (v) => {
    value.value = String(v)
  }
)

const options = [
  { value: '1', label: '1 reviewer (single screening)' },
  { value: '2', label: '2 reviewers (dual screening, conflicts to owner)' },
]

const onChange = async (v: string | number) => {
  const next = Number(v)
  if (next !== 1 && next !== 2) return
  value.value = String(next)
  saving.value = true
  const updated = await projectsStore.updateProject(props.project.id, { required_reviewers: next })
  saving.value = false
  if (updated) {
    wsStore.addNotification(`Required reviewers set to ${next}`, 'success')
  } else {
    value.value = String(props.project.required_reviewers)
    wsStore.addNotification(projectsStore.error ?? 'Failed to update setting', 'error')
  }
}
</script>

<template>
  <Card class="p-6 space-y-3">
    <div>
      <h3 class="font-semibold">Screening Settings</h3>
      <p class="text-sm text-muted-foreground mt-1">
        Number of human reviewers who must decide on each article and stage. With two reviewers,
        screening is blinded and disagreements go to the owner as conflicts.
      </p>
    </div>
    <div class="space-y-2 max-w-md">
      <Label for="required-reviewers">Required reviewers</Label>
      <Select
        id="required-reviewers"
        :model-value="value"
        :options="options"
        :disabled="!canEdit || saving"
        @update:model-value="onChange"
      />
      <p v-if="!canEdit" class="text-xs text-muted-foreground">Only the owner can change this.</p>
    </div>
  </Card>
</template>
