<script setup lang="ts">
import AppLayout from '@/components/layout/AppLayout.vue'

const links = [
  { name: 'admin-overview', label: 'Overview' },
  { name: 'admin-users', label: 'Users' },
  { name: 'admin-projects', label: 'Projects' },
  { name: 'admin-payments', label: 'Payments' },
]
</script>

<template>
  <AppLayout>
    <div class="space-y-6">
      <div>
        <h1 class="text-3xl font-bold">Admin</h1>
        <p class="mt-2 text-muted-foreground">Users, plans and payments across Excludr</p>
      </div>
      <nav class="inline-flex flex-wrap gap-1 rounded-md bg-muted p-1" aria-label="Admin sections">
        <router-link
          v-for="link in links"
          :key="link.name"
          :to="{ name: link.name }"
          class="rounded-sm px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
          :exact-active-class="'bg-background text-foreground shadow-sm'"
          :active-class="link.name === 'admin-overview' ? '' : 'bg-background text-foreground shadow-sm'"
        >
          {{ link.label }}
        </router-link>
      </nav>
      <router-view />
    </div>
  </AppLayout>
</template>
