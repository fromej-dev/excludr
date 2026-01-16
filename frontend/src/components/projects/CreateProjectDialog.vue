<script setup lang="ts">
import { ref, watch } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import Dialog from '@/components/ui/Dialog.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Textarea from '@/components/ui/Textarea.vue'

interface Props {
  open: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'created': []
}>()

const projectsStore = useProjectsStore()

const name = ref('')
const description = ref('')
const reviewQuestion = ref('')

const resetForm = () => {
  name.value = ''
  description.value = ''
  reviewQuestion.value = ''
}

const handleSubmit = async () => {
  const project = await projectsStore.createProject({
    name: name.value,
    description: description.value || undefined,
    review_question: reviewQuestion.value || undefined,
  })

  if (project) {
    resetForm()
    emit('update:open', false)
    emit('created')
  }
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) {
    resetForm()
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)" title="Create New Project">
    <form @submit.prevent="handleSubmit" class="space-y-4">
      <div class="space-y-2">
        <Label for="project-name">Project Name</Label>
        <Input
          id="project-name"
          v-model="name"
          placeholder="Enter project name"
          required
        />
      </div>

      <div class="space-y-2">
        <Label for="project-description">Description (Optional)</Label>
        <Textarea
          id="project-description"
          v-model="description"
          placeholder="Brief description of the systematic review"
          :rows="3"
        />
      </div>

      <div class="space-y-2">
        <Label for="review-question">Review Question (Optional)</Label>
        <Textarea
          id="review-question"
          v-model="reviewQuestion"
          placeholder="What is the research question?"
          :rows="3"
        />
      </div>

      <div class="flex justify-end gap-3">
        <Button
          type="button"
          variant="outline"
          @click="$emit('update:open', false)"
        >
          Cancel
        </Button>
        <Button type="submit" :disabled="projectsStore.loading">
          {{ projectsStore.loading ? 'Creating...' : 'Create Project' }}
        </Button>
      </div>
    </form>
  </Dialog>
</template>
