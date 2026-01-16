<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectsStore } from '@/stores/projects'
import AppLayout from '@/components/layout/AppLayout.vue'
import Tabs from '@/components/ui/Tabs.vue'
import TabsList from '@/components/ui/TabsList.vue'
import TabsTrigger from '@/components/ui/TabsTrigger.vue'
import TabsContent from '@/components/ui/TabsContent.vue'

const route = useRoute()
const router = useRouter()
const projectsStore = useProjectsStore()

const projectId = computed(() => Number(route.params.id))
const currentTab = computed(() => {
  const name = route.name as string
  if (name === 'project-criteria') return 'criteria'
  if (name === 'project-articles') return 'articles'
  if (name === 'article-detail') return 'articles'
  if (name === 'project-screening') return 'screening'
  return 'overview'
})

onMounted(() => {
  projectsStore.fetchProject(projectId.value)
})

const navigateToTab = (tab: string) => {
  const routes: Record<string, string> = {
    overview: 'project-overview',
    criteria: 'project-criteria',
    articles: 'project-articles',
    screening: 'project-screening',
  }
  router.push({ name: routes[tab], params: { id: projectId.value } })
}
</script>

<template>
  <AppLayout>
    <div class="space-y-6">
      <div>
        <h1 class="text-3xl font-bold">{{ projectsStore.currentProject?.name }}</h1>
      </div>

      <Tabs :model-value="currentTab" @update:model-value="navigateToTab">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="criteria">Criteria</TabsTrigger>
          <TabsTrigger value="articles">Articles</TabsTrigger>
          <TabsTrigger value="screening">Screening</TabsTrigger>
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
      </Tabs>
    </div>
  </AppLayout>
</template>
