<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/Button.vue'

const authStore = useAuthStore()
const router = useRouter()

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="container flex h-16 items-center justify-between px-4">
      <div class="flex items-center gap-6">
        <router-link to="/" class="flex items-center space-x-2">
          <span class="text-xl font-bold">Excludr</span>
        </router-link>
        <nav v-if="authStore.isAuthenticated" class="flex items-center gap-4">
          <router-link to="/" class="text-sm font-medium hover:text-primary">
            Projects
          </router-link>
        </nav>
      </div>

      <div v-if="authStore.isAuthenticated" class="flex items-center gap-4">
        <span class="text-sm text-muted-foreground">{{ authStore.user?.name }}</span>
        <Button variant="ghost" size="sm" @click="handleLogout">
          Logout
        </Button>
      </div>
    </div>
  </header>
</template>
