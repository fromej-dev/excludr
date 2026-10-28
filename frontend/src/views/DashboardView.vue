<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import ProjectCard from '@/components/projects/ProjectCard.vue'
import CreateProjectDialog from '@/components/projects/CreateProjectDialog.vue'
import Button from '@/components/ui/Button.vue'

const projectsStore = useProjectsStore()
const authStore = useAuthStore()
const showCreateDialog = ref(false)

onMounted(() => {
  projectsStore.fetchProjects()
})

const handleProjectCreated = () => {
  projectsStore.fetchProjects()
}

const firstName = computed(() => authStore.user?.name?.trim().split(/\s+/)[0] ?? '')
const isEmpty = computed(() => !projectsStore.loading && !projectsStore.error && projectsStore.projects.length === 0)

const steps = [
  { title: 'Create a project', body: 'Name your review and write down the review question.' },
  { title: 'Import articles', body: 'Upload a RIS or PubMed export from your database search.' },
  { title: 'Define criteria', body: 'Add the inclusion and exclusion criteria articles are judged against.' },
  { title: 'Screen', body: 'Screen yourself, with a co-reviewer, or let the AI agent suggest decisions.' },
]
</script>

<template>
  <AppLayout>
    <div class="space-y-8">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div class="min-w-0">
          <p v-if="firstName" class="text-sm font-medium text-muted-foreground">Welcome back, {{ firstName }}</p>
          <h1 class="text-2xl font-bold tracking-tight sm:text-3xl">Projects</h1>
        </div>
        <Button data-testid="create-project" class="gap-1.5" @click="showCreateDialog = true">
          <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New project
        </Button>
      </div>

      <div v-if="projectsStore.loading && projectsStore.projects.length === 0" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy="true">
        <span class="sr-only">Loading projects...</span>
        <div v-for="i in 3" :key="i" class="h-40 animate-pulse rounded-lg border bg-card" />
      </div>

      <div v-else-if="projectsStore.error" class="rounded-md bg-destructive/15 p-4 text-destructive">
        {{ projectsStore.error }}
      </div>

      <section
        v-else-if="isEmpty"
        class="overflow-hidden rounded-xl border bg-card"
        aria-labelledby="empty-title"
      >
        <div class="flex flex-col items-center px-6 pb-8 pt-10 text-center sm:px-10">
          <span class="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/15 text-primary" aria-hidden="true">
            <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2zM12 10v6M9 13h6" />
            </svg>
          </span>
          <p class="mt-5 text-sm font-medium text-muted-foreground">No projects yet</p>
          <h2 id="empty-title" class="mt-1 text-xl font-semibold">Start your first review</h2>
          <p class="mt-2 max-w-md text-sm text-muted-foreground">
            A project holds one systematic review: its articles, criteria and every screening decision.
          </p>
          <Button data-testid="create-first-project" size="lg" class="mt-6 px-6" @click="showCreateDialog = true">
            Create your first project
          </Button>
        </div>
        <ol class="grid gap-px border-t bg-border sm:grid-cols-2 lg:grid-cols-4">
          <li v-for="(step, i) in steps" :key="step.title" class="flex gap-3 bg-card p-5">
            <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold tabular-nums text-secondary-foreground">
              {{ i + 1 }}
            </span>
            <div>
              <p class="text-sm font-medium">{{ step.title }}</p>
              <p class="mt-0.5 text-sm text-muted-foreground">{{ step.body }}</p>
            </div>
          </li>
        </ol>
      </section>

      <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <ProjectCard
          v-for="project in projectsStore.projects"
          :key="project.id"
          :project="project"
        />
      </div>

      <CreateProjectDialog
        v-model:open="showCreateDialog"
        @created="handleProjectCreated"
      />
    </div>
  </AppLayout>
</template>
