<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const links = computed(() =>
  [
    { name: 'admin-overview', label: 'Overview' },
    { name: 'admin-users', label: 'Users', also: ['admin-user'] },
    { name: 'admin-projects', label: 'Projects' },
    { name: 'admin-payments', label: 'Payments' },
    { name: 'admin-ai-usage', label: 'AI usage' },
  ].map((l) => ({ ...l, active: route.name === l.name || (l.also ?? []).includes(route.name as string) }))
)
</script>

<template>
  <div data-testid="admin-sidebar">
    <p class="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Admin</p>
    <nav aria-label="Admin sections">
      <ul class="space-y-0.5">
        <li v-for="link in links" :key="link.name">
          <router-link
            :to="{ name: link.name }"
            :aria-current="link.active ? 'page' : undefined"
            class="flex items-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :class="link.active ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'"
          >
            {{ link.label }}
          </router-link>
        </li>
      </ul>
    </nav>
  </div>
</template>
