<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import { useMembersStore } from '@/stores/members'
import { useConflictsStore } from '@/stores/conflicts'
import { useProjectNavStore } from '@/stores/projectNav'
import { useProjectStatsStore } from '@/stores/projectStats'
import { useProjectLiveUpdates } from '@/composables/useProjectLiveUpdates'
import { useBillingStore } from '@/stores/billing'
import AppLayout from '@/components/layout/AppLayout.vue'
import ProjectSidebar from '@/components/layout/ProjectSidebar.vue'

const route = useRoute()
const projectsStore = useProjectsStore()
const membersStore = useMembersStore()
const conflictsStore = useConflictsStore()
const navStore = useProjectNavStore()
const statsStore = useProjectStatsStore()
const billingStore = useBillingStore()

const projectId = computed(() => Number(route.params.id))

// Load the project and the signed-in user's role in it (drives which links/actions show)
watch(
  projectId,
  (id) => {
    membersStore.reset()
    navStore.reset()
    statsStore.reset()
    projectsStore.fetchProject(id)
    membersStore.fetchMyRole(id)
    membersStore.fetchMembers(id)
    billingStore.fetchStatus(id)
  },
  { immediate: true }
)

const isScreening = computed(() => route.name === 'project-screening')
// The overview renders its own page heading
const isOverview = computed(() => route.name === 'project-overview')

// Refresh sidebar counts when the project/role is known and on every route change within the project
const refreshNav = () => {
  if (membersStore.role === null) return
  void navStore.refresh(projectId.value, { canReview: membersStore.canReview, isOwner: membersStore.isOwner })
}
watch(() => [projectId.value, membersStore.role, route.name, route.params.articleId], refreshNav, { immediate: true })

// Screening stats (Overview progress, next step, screening toolbar): load per project and refresh on
// every page change within it, keeping the last numbers on screen while the refresh runs
watch([projectId, () => route.name], () => void statsStore.fetch(projectId.value), { immediate: true })

// While a bulk job (full-text retrieval, AI batch) runs, keep stats and sidebar counts live
useProjectLiveUpdates(projectId, (id) => {
  void statsStore.fetch(id)
  if (membersStore.canReview) void navStore.refreshScreening(id)
})

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
    <template #sidebar>
      <ProjectSidebar />
    </template>

    <div class="min-w-0" :class="isScreening ? 'space-y-3' : 'space-y-6'">
      <h1
        v-if="!isOverview"
        class="truncate"
        :class="isScreening ? 'sr-only' : 'text-2xl font-bold lg:text-3xl'"
      >
        {{ projectsStore.currentProject?.name }}
      </h1>
      <div
        v-if="billingStore.status?.read_only"
        role="status"
        data-testid="read-only-banner"
        class="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm"
      >
        This review's pass has expired, so the project is read-only. You can still view and
        export everything.
        <router-link
          v-if="!isOverview"
          :to="{ name: 'project-overview', params: { id: projectId } }"
          class="ml-1 font-medium text-primary hover:underline"
        >
          Renew the pass
        </router-link>
      </div>
      <router-view />
    </div>
  </AppLayout>
</template>
