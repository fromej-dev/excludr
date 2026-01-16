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

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()

const project = computed(() => projectsStore.currentProject)
const projectId = computed(() => Number(route.params.id))

const isEditing = ref(false)
const editName = ref('')
const editDescription = ref('')
const editReviewQuestion = ref('')

const showUploadDialog = ref(false)
const uploadFile = ref<File | null>(null)
const uploadProgress = ref(false)

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

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    uploadFile.value = target.files[0]
  }
}

const handleUpload = async () => {
  if (!uploadFile.value) return

  uploadProgress.value = true
  await projectsStore.uploadFile(projectId.value, uploadFile.value)
  uploadProgress.value = false

  showUploadDialog.value = false
  uploadFile.value = null
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
          <div class="flex gap-2">
            <Button variant="outline" @click="startEdit">Edit</Button>
            <Button variant="destructive" @click="showDeleteDialog = true">Delete</Button>
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

    <Card class="p-6">
      <h3 class="font-semibold mb-4">Upload Articles</h3>
      <p class="text-sm text-muted-foreground mb-4">
        Upload a file containing articles for screening. Supported formats: RIS (.ris), PubMed CSV (.csv), or MEDLINE (.txt).
      </p>
      <Button @click="showUploadDialog = true">Upload File</Button>
    </Card>

    <Dialog v-model:open="showUploadDialog" title="Upload Article File">
      <div class="space-y-4">
        <div class="space-y-2">
          <Label for="article-file">Select File</Label>
          <input
            id="article-file"
            type="file"
            accept=".ris,.csv,.txt"
            @change="handleFileSelect"
            class="block w-full text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
          />
          <p class="text-xs text-muted-foreground">
            Accepted formats: .ris, .csv (PubMed), .txt (MEDLINE)
          </p>
        </div>

        <div class="flex justify-end gap-3">
          <Button type="button" variant="outline" @click="showUploadDialog = false">
            Cancel
          </Button>
          <Button @click="handleUpload" :disabled="!uploadFile || uploadProgress">
            {{ uploadProgress ? 'Uploading...' : 'Upload' }}
          </Button>
        </div>
      </div>
    </Dialog>

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
