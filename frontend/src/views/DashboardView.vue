<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useProjectsStore } from '@/stores/projects'
import AppLayout from '@/components/layout/AppLayout.vue'
import ProjectCard from '@/components/projects/ProjectCard.vue'
import CreateProjectDialog from '@/components/projects/CreateProjectDialog.vue'
import Button from '@/components/ui/Button.vue'

const projectsStore = useProjectsStore()
const showCreateDialog = ref(false)

onMounted(() => {
  projectsStore.fetchProjects()
})

const handleProjectCreated = () => {
  projectsStore.fetchProjects()
}
</script>

<template>
  <AppLayout>
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-bold">Projects</h1>
          <p class="mt-2 text-muted-foreground">
            Manage your systematic review projects
          </p>
        </div>
        <Button @click="showCreateDialog = true">
          Create Project
        </Button>
      </div>

      <div v-if="projectsStore.loading" class="text-center py-12">
        <p class="text-muted-foreground">Loading projects...</p>
      </div>

      <div v-else-if="projectsStore.error" class="rounded-md bg-destructive/15 p-4 text-destructive">
        {{ projectsStore.error }}
      </div>

      <div
        v-else-if="projectsStore.projects.length === 0"
        class="text-center py-12"
      >
        <p class="text-muted-foreground mb-4">No projects yet</p>
        <Button @click="showCreateDialog = true">
          Create your first project
        </Button>
      </div>

      <div v-else class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
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
