<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
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
import FullTextBatchCard from '@/components/articles/FullTextBatchCard.vue'
import ReviewSettingsCard from '@/components/projects/ReviewSettingsCard.vue'
import { useMembersStore } from '@/stores/members'
import { useScreeningStore } from '@/stores/screening'
import { useProjectNavStore } from '@/stores/projectNav'
import NextStepCard from '@/components/overview/NextStepCard.vue'
import ReviewProgress from '@/components/overview/ReviewProgress.vue'
import SetupChecklist from '@/components/overview/SetupChecklist.vue'
import type { ChecklistItem } from '@/components/overview/SetupChecklist.vue'
import { computeNextStep } from '@/utils/nextStep'

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()
const membersStore = useMembersStore()

const screeningStore = useScreeningStore()
const navStore = useProjectNavStore()
const { stats } = storeToRefs(screeningStore)
const { pendingTitleAbstract, pendingFullText, conflicts, criteria } = storeToRefs(navStore)


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

const statsReady = ref(false)
const loadStats = async () => {
  statsReady.value = false
  screeningStore.stats = null
  await screeningStore.fetchStats(projectId.value)
  statsReady.value = true
}
watch(projectId, loadStats, { immediate: true })

const currentStats = computed(() => (statsReady.value ? stats.value : null))

const nextStep = computed(() =>
  computeNextStep({
    settled: membersStore.roleSettled && statsReady.value && (membersStore.role === null || navStore.settled),
    role: membersStore.role,
    criteriaCount: criteria.value,
    totalArticles: project.value?.number_of_articles ?? 0,
    stats: currentStats.value,
    pendingTitleAbstract: pendingTitleAbstract.value,
    pendingFullText: pendingFullText.value,
    conflicts: conflicts.value,
  })
)

const checklist = computed<ChecklistItem[]>(() => [
  {
    key: 'criteria',
    label: 'Define inclusion/exclusion criteria',
    done: (criteria.value ?? 0) > 0,
    to: { name: 'project-criteria', params: { id: projectId.value } },
  },
  { key: 'articles', label: 'Import articles', done: (project.value?.number_of_articles ?? 0) > 0, anchor: 'import' },
  {
    key: 'reviewers',
    label: 'Invite reviewers',
    done: membersStore.members.length > 1 || project.value?.required_reviewers === 1,
    to: { name: 'project-members', params: { id: projectId.value } },
  },
])
// Only owners can act on the checklist; hide it once everything is done (and while data is loading)
const showChecklist = computed(
  () => isOwner.value && criteria.value !== null && checklist.value.some((i) => !i.done)
)

const retryNextStep = async () => {
  if (membersStore.role === null) await membersStore.fetchMyRole(projectId.value)
  await Promise.all([
    loadStats(),
    membersStore.role === null
      ? undefined
      : navStore.refresh(projectId.value, { canReview: membersStore.canReview, isOwner: membersStore.isOwner }),
  ])
}

const scrollToSection = async (id: string) => {
  await nextTick()
  const el = document.getElementById(id)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  el?.focus({ preventScroll: true })
}

// Refresh the project (article count), stats and sidebar counts after an import
const onImported = async () => {
  await projectsStore.fetchProject(projectId.value)
  void loadStats()
  if (membersStore.canReview) void navStore.refreshScreening(projectId.value)
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
    <!-- Header -->
    <header class="space-y-4" data-testid="project-header">
      <div v-if="!isEditing" class="space-y-4">
        <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div class="min-w-0">
            <h1 class="break-words text-3xl font-bold">{{ project?.name }}</h1>
            <p class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              <Badge v-if="membersStore.role" variant="secondary" class="capitalize" data-testid="role-badge">
                {{ membersStore.role }}
              </Badge>
              <span>
                Created {{ project?.created_at ? new Date(project.created_at).toLocaleDateString() : '' }}
              </span>
              <span>{{ project?.number_of_articles || 0 }} articles</span>
            </p>
          </div>
          <Button v-if="isOwner" variant="outline" @click="startEdit">Edit</Button>
        </div>

        <figure v-if="project?.review_question" class="border-l-4 border-ai pl-4" data-testid="review-question">
          <figcaption class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Review question
          </figcaption>
          <p class="mt-1 text-xl font-medium leading-snug">{{ project.review_question }}</p>
        </figure>
        <p v-else-if="isOwner" class="text-sm text-muted-foreground">
          No review question yet. Add one with Edit; it anchors every screening decision.
        </p>

        <p v-if="project?.description" class="text-muted-foreground">{{ project.description }}</p>
      </div>

      <Card v-else class="p-6">
        <h1 class="sr-only">{{ project?.name }}</h1>
        <form @submit.prevent="saveEdit" class="space-y-4">
          <h2 class="text-lg font-semibold">Project settings</h2>
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
    </header>

    <NextStepCard :step="nextStep" @anchor="scrollToSection" @retry="retryNextStep" />

    <ReviewProgress :stats="currentStats" :pending-full-text="pendingFullText" />

    <SetupChecklist v-if="showChecklist" :items="checklist" @anchor="scrollToSection" />

    <section class="space-y-4" aria-labelledby="manage-heading">
      <h2 id="manage-heading" class="text-lg font-semibold">Manage</h2>
      <div id="settings" tabindex="-1" class="scroll-mt-24 focus:outline-none">
        <ReviewSettingsCard v-if="project" :project="project" :can-edit="isOwner" />
      </div>
      <div id="import" tabindex="-1" class="scroll-mt-24 focus:outline-none">
        <ImportCard :project-id="projectId" :can-upload="isOwner" @imported="onImported" />
      </div>
      <div id="fulltext" tabindex="-1" class="scroll-mt-24 focus:outline-none">
        <FullTextBatchCard :project-id="projectId" :can-run="isOwner" />
      </div>
    </section>

    <section
      v-if="isOwner"
      class="rounded-lg border border-exclude/50 p-5"
      aria-labelledby="danger-heading"
      data-testid="danger-zone"
    >
      <h2 id="danger-heading" class="text-lg font-semibold">Danger zone</h2>
      <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
        <p class="text-sm text-muted-foreground">Deleting a project removes its articles, criteria and decisions for good.</p>
        <Button variant="destructive" @click="showDeleteDialog = true">Delete</Button>
      </div>
    </section>

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
