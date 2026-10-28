<script setup lang="ts">
import { computed } from 'vue'
import type { Project } from '@/types'

interface Props {
  project: Project
}

const props = defineProps<Props>()

const formattedDate = computed(() => {
  return new Date(props.project.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
})
</script>

<template>
  <router-link
    :to="`/projects/${project.id}`"
    class="group flex flex-col rounded-lg border bg-card p-5 text-card-foreground shadow-sm transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
  >
    <h3 class="line-clamp-2 text-base font-semibold group-hover:text-primary">{{ project.name }}</h3>

    <p v-if="project.description" class="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
      {{ project.description }}
    </p>

    <p v-if="project.review_question" class="mt-3 line-clamp-2 border-l-2 pl-3 text-sm italic text-muted-foreground">
      {{ project.review_question }}
    </p>

    <div class="mt-auto flex items-center justify-between gap-2 pt-4 text-xs text-muted-foreground">
      <span class="tabular-nums">
        <span class="font-semibold text-foreground">{{ project.number_of_articles }}</span>
        {{ project.number_of_articles === 1 ? 'article' : 'articles' }}
        <template v-if="project.required_reviewers === 2"> · dual screening</template>
      </span>
      <span>{{ formattedDate }}</span>
    </div>
  </router-link>
</template>
