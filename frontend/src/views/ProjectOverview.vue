<script setup lang="ts">
import { ref, computed } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import { useRoute, useRouter } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Textarea from '@/components/ui/Textarea.vue'
import Card from '@/components/ui/Card.vue'
import Dialog from '@/components/ui/Dialog.vue'
import Badge from '@/components/ui/Badge.vue'
import ImportCard from '@/components/projects/ImportCard.vue'
import ReviewSettingsCard from '@/components/projects/ReviewSettingsCard.vue'
import { useMembersStore } from '@/stores/members'

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()
const membersStore = useMembersStore()

const isOwner = computed(() => membersStore.isOwner)

const project = computed(() => projectsStore.currentProject)
const projectId = computed(() => Number(route.params.id))

const isEditing = ref(false)
const editName = ref('')
const editDescription = ref('')
const editReviewQuestion = ref('')

const showDeleteDialog = ref(false)

const startEdit = () => {
  if (project.value) {
    editName.value = project.value.name
    editDescription.value = project.value.description || ''
    editReviewQuestion.value = project.value.review_question || ''
    isEditing.value = true
  }
}

const saveEdit = async () => {
  if (!project.value) return

  await projectsStore.updateProject(project.value.id, {
    name: editName.value,
    description: editDescription.value || undefined,
    review_question: editReviewQuestion.value || undefined,
  })

  isEditing.value = false
}

const cancelEdit = () => {
  isEditing.value = false
}

// Refresh the project (article count) after an import
const onImported = () => {
  projectsStore.fetchProject(projectId.value)
}

const handleDelete = async () => {
  const success = await projectsStore.deleteProject(projectId.value)
  if (success) {
    router.push('/')
  }
}
</script>

<template>
  <div class="space-y-6">
    <Card class="p-6">
      <div v-if="!isEditing">
        <div class="flex items-start justify-between mb-4">
          <div>
            <h2 class="text-2xl font-bold">{{ project?.name }}</h2>
            <p class="text-sm text-muted-foreground mt-1">
              Created {{ project?.created_at ? new Date(project.created_at).toLocaleDateString() : '' }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <Badge v-if="membersStore.role" variant="secondary" class="capitalize" data-testid="role-badge">
              {{ membersStore.role }}
            </Badge>
            <template v-if="isOwner">
            <Button variant="outline" @click="startEdit">Edit</Button>
            <Button variant="destructive" @click="showDeleteDialog = true">Delete</Button>
            </template>
          </div>
        </div>

        <div class="space-y-4">
          <div v-if="project?.description">
            <h3 class="font-semibold mb-2">Description</h3>
            <p class="text-muted-foreground">{{ project.description }}</p>
          </div>

          <div v-if="project?.review_question">
            <h3 class="font-semibold mb-2">Review Question</h3>
            <p class="text-muted-foreground">{{ project.review_question }}</p>
          </div>

          <div>
            <h3 class="font-semibold mb-2">Statistics</h3>
            <p class="text-muted-foreground">
              {{ project?.number_of_articles || 0 }} articles
            </p>
          </div>
        </div>
      </div>

      <form v-else @submit.prevent="saveEdit" class="space-y-4">
        <div class="space-y-2">
          <Label for="edit-name">Project Name</Label>
          <Input id="edit-name" v-model="editName" required />
        </div>

        <div class="space-y-2">
          <Label for="edit-description">Description</Label>
          <Textarea id="edit-description" v-model="editDescription" :rows="3" />
        </div>

        <div class="space-y-2">
          <Label for="edit-review-question">Review Question</Label>
          <Textarea id="edit-review-question" v-model="editReviewQuestion" :rows="3" />
        </div>

        <div class="flex justify-end gap-3">
          <Button type="button" variant="outline" @click="cancelEdit">Cancel</Button>
          <Button type="submit">Save Changes</Button>
        </div>
      </form>
    </Card>

    <ReviewSettingsCard v-if="project" :project="project" :can-edit="isOwner" />

    <ImportCard :project-id="projectId" :can-upload="isOwner" @imported="onImported" />

    <Dialog v-model:open="showDeleteDialog" title="Delete Project">
      <div class="space-y-4">
        <p class="text-sm">
          Are you sure you want to delete this project? This action cannot be undone.
        </p>

        <div class="flex justify-end gap-3">
          <Button type="button" variant="outline" @click="showDeleteDialog = false">
            Cancel
          </Button>
          <Button variant="destructive" @click="handleDelete">
            Delete Project
          </Button>
        </div>
      </div>
    </Dialog>
  </div>
</template>
