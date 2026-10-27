<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import { useMembersStore } from '@/stores/members'
import { useConflictsStore } from '@/stores/conflicts'
import { useProjectNavStore } from '@/stores/projectNav'
import AppLayout from '@/components/layout/AppLayout.vue'
import ProjectSidebar from '@/components/layout/ProjectSidebar.vue'

const route = useRoute()
const projectsStore = useProjectsStore()
const membersStore = useMembersStore()
const conflictsStore = useConflictsStore()
const navStore = useProjectNavStore()

const projectId = computed(() => Number(route.params.id))

// Load the project and the signed-in user's role in it (drives which links/actions show)
watch(
  projectId,
  (id) => {
    membersStore.reset()
    navStore.reset()
    projectsStore.fetchProject(id)
    membersStore.fetchMyRole(id)
    membersStore.fetchMembers(id)
  },
  { immediate: true }
)

const isScreening = computed(() => route.name === 'project-screening')

// Refresh sidebar counts when the project/role is known and on every route change within the project
const refreshNav = () => {
  if (membersStore.role === null) return
  void navStore.refresh(projectId.value, { canReview: membersStore.canReview, isOwner: membersStore.isOwner })
}
watch(() => [projectId.value, membersStore.role, route.name, route.params.articleId], refreshNav, { immediate: true })

// Keep the conflicts badge in step when conflicts are resolved on the Conflicts page
watch(
  () => conflictsStore.conflicts.length,
  (n) => {
    if (route.name === 'project-conflicts' && !conflictsStore.loading) navStore.setConflicts(n)
  }
)
</script>

<template>
  <AppLayout :full-width="isScreening">
    <div class="space-y-3 lg:flex lg:items-start lg:gap-8 lg:space-y-0">
      <ProjectSidebar />

      <div class="min-w-0 flex-1" :class="isScreening ? 'space-y-3' : 'space-y-6'">
        <h1
          :class="isScreening ? 'sr-only' : 'max-lg:sr-only text-3xl font-bold'"
        >
          {{ projectsStore.currentProject?.name }}
        </h1>
        <router-view />
      </div>
    </div>
  </AppLayout>
</template>
