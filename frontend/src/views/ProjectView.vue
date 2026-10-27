<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import { useMembersStore } from '@/stores/members'
import AppLayout from '@/components/layout/AppLayout.vue'
import Tabs from '@/components/ui/Tabs.vue'
import TabsList from '@/components/ui/TabsList.vue'
import TabsTrigger from '@/components/ui/TabsTrigger.vue'
import TabsContent from '@/components/ui/TabsContent.vue'

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()
const membersStore = useMembersStore()

const projectId = computed(() => Number(route.params.id))
const currentTab = computed(() => {
  const name = route.name as string
  if (name === 'project-criteria') return 'criteria'
  if (name === 'project-articles') return 'articles'
  if (name === 'article-detail') return 'articles'
  if (name === 'project-screening') return 'screening'
  if (name === 'project-members') return 'members'
  if (name === 'project-conflicts') return 'conflicts'
  if (name === 'project-reports') return 'reports'
  if (name === 'project-audit') return 'audit'
  return 'overview'
})

// Load the project and the signed-in user's role in it (drives which tabs/actions show)
watch(
  projectId,
  (id) => {
    membersStore.reset()
    projectsStore.fetchProject(id)
    membersStore.fetchMyRole(id)
    membersStore.fetchMembers(id)
  },
  { immediate: true }
)

const isScreening = computed(() => currentTab.value === 'screening')
const isOwner = computed(() => membersStore.isOwner)

const navigateToTab = (tab: string) => {
  const routes: Record<string, string> = {
    overview: 'project-overview',
    criteria: 'project-criteria',
    articles: 'project-articles',
    screening: 'project-screening',
    members: 'project-members',
    conflicts: 'project-conflicts',
    reports: 'project-reports',
    audit: 'project-audit',
  }
  router.push({ name: routes[tab], params: { id: projectId.value } })
}
</script>

<template>
  <AppLayout :full-width="isScreening">
    <div :class="isScreening ? 'space-y-3' : 'space-y-6'">
      <div>
        <h1 :class="isScreening ? 'text-xl font-bold' : 'text-3xl font-bold'">{{ projectsStore.currentProject?.name }}</h1>
      </div>

      <Tabs :model-value="currentTab" @update:model-value="navigateToTab">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="criteria">Criteria</TabsTrigger>
          <TabsTrigger value="articles">Articles</TabsTrigger>
          <TabsTrigger value="screening">Screening</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger v-if="isOwner" value="conflicts">Conflicts</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger v-if="isOwner" value="audit">Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <router-view />
        </TabsContent>
        <TabsContent value="criteria">
          <router-view />
        </TabsContent>
        <TabsContent value="articles">
          <router-view />
        </TabsContent>
        <TabsContent value="screening">
          <router-view />
        </TabsContent>
        <TabsContent value="members">
          <router-view />
        </TabsContent>
        <TabsContent value="conflicts">
          <router-view />
        </TabsContent>
        <TabsContent value="reports">
          <router-view />
        </TabsContent>
        <TabsContent value="audit">
          <router-view />
        </TabsContent>
      </Tabs>
    </div>
  </AppLayout>
</template>
