<script setup lang="ts">
import AppLayout from '@/components/layout/AppLayout.vue'
import AdminSidebar from '@/components/layout/AdminSidebar.vue'
</script>

<template>
  <AppLayout>
    <template #sidebar>
      <AdminSidebar />
    </template>

    <div class="space-y-6">
      <div>
        <h1 class="text-3xl font-bold">Admin</h1>
        <p class="mt-2 text-muted-foreground">Users, plans, payments and AI usage across Excludr</p>
      </div>
      <router-view />
    </div>
  </AppLayout>
</template>
