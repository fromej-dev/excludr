<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { Project } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'

interface Props {
  project: Project
}

const props = defineProps<Props>()
const router = useRouter()

const formattedDate = computed(() => {
  return new Date(props.project.created_at).toLocaleDateString()
})

const goToProject = () => {
  router.push(`/projects/${props.project.id}`)
}
</script>

<template>
  <Card
    class="cursor-pointer p-6 transition-all hover:shadow-lg"
    @click="goToProject"
  >
    <div class="space-y-3">
      <div class="flex items-start justify-between">
        <h3 class="text-xl font-semibold">{{ project.name }}</h3>
        <Badge>{{ project.number_of_articles }} articles</Badge>
      </div>

      <p v-if="project.description" class="text-sm text-muted-foreground line-clamp-2">
        {{ project.description }}
      </p>

      <div v-if="project.review_question" class="text-sm">
        <span class="font-medium">Review Question:</span>
        <p class="mt-1 text-muted-foreground line-clamp-2">{{ project.review_question }}</p>
      </div>

      <div class="flex items-center justify-between pt-2 text-xs text-muted-foreground">
        <span>Created {{ formattedDate }}</span>
      </div>
    </div>
  </Card>
</template>
