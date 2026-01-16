<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Criterion, CriterionType } from '@/types'
import Dialog from '@/components/ui/Dialog.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Textarea from '@/components/ui/Textarea.vue'

interface Props {
  open: boolean
  criterion?: Criterion
  type: CriterionType
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  submit: [data: { code: string; description: string; rationale?: string }]
}>()

const code = ref('')
const description = ref('')
const rationale = ref('')

const resetForm = () => {
  code.value = ''
  description.value = ''
  rationale.value = ''
}

watch(() => props.open, (isOpen) => {
  if (isOpen && props.criterion) {
    code.value = props.criterion.code
    description.value = props.criterion.description
    rationale.value = props.criterion.rationale || ''
  } else if (!isOpen) {
    resetForm()
  }
})

const handleSubmit = () => {
  emit('submit', {
    code: code.value,
    description: description.value,
    rationale: rationale.value || undefined,
  })
  resetForm()
}
</script>

<template>
  <Dialog
    :open="open"
    @update:open="$emit('update:open', $event)"
    :title="criterion ? 'Edit Criterion' : `Add ${type === 'inclusion' ? 'Inclusion' : 'Exclusion'} Criterion`"
  >
    <form @submit.prevent="handleSubmit" class="space-y-4">
      <div class="space-y-2">
        <Label for="code">Code</Label>
        <Input
          id="code"
          v-model="code"
          :placeholder="type === 'inclusion' ? 'I1' : 'E1'"
          maxlength="10"
          required
        />
        <p class="text-xs text-muted-foreground">
          Short identifier (e.g., I1, I2 for inclusion; E1, E2 for exclusion)
        </p>
      </div>

      <div class="space-y-2">
        <Label for="description">Description</Label>
        <Textarea
          id="description"
          v-model="description"
          placeholder="Describe the criterion"
          :rows="3"
          required
        />
      </div>

      <div class="space-y-2">
        <Label for="rationale">Rationale (Optional)</Label>
        <Textarea
          id="rationale"
          v-model="rationale"
          placeholder="Explain why this criterion is important"
          :rows="3"
        />
      </div>

      <div class="flex justify-end gap-3">
        <Button type="button" variant="outline" @click="$emit('update:open', false)">
          Cancel
        </Button>
        <Button type="submit">
          {{ criterion ? 'Update' : 'Add' }} Criterion
        </Button>
      </div>
    </form>
  </Dialog>
</template>
