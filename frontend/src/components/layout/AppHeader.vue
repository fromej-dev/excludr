<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import { useTheme, type ThemeMode } from '@/composables/useTheme'

const authStore = useAuthStore()
const router = useRouter()

const { mode, setMode } = useTheme()

// Lucide-style 24x24 stroke icon paths.
const themeOptions: { value: ThemeMode; label: string; icon: string }[] = [
  {
    value: 'light',
    label: 'Light',
    icon: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41',
  },
  { value: 'system', label: 'System', icon: 'M3 4h18a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 21h8M12 17v4' },
  { value: 'dark', label: 'Dark', icon: 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z' },
]

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="container flex h-16 items-center justify-between gap-2 px-4">
      <div class="flex min-w-0 items-center gap-3 sm:gap-6">
        <router-link to="/dashboard" class="flex items-center space-x-2">
          <span class="text-xl font-bold">Excludr</span>
        </router-link>
        <nav v-if="authStore.isAuthenticated" class="flex items-center gap-4">
          <router-link to="/dashboard" class="text-sm font-medium hover:text-primary">
            Projects
          </router-link>
          <router-link
            v-if="authStore.user?.is_superuser"
            to="/admin"
            class="text-sm font-medium hover:text-primary"
            data-testid="admin-link"
          >
            Admin
          </router-link>
        </nav>
      </div>

      <div class="flex shrink-0 items-center gap-2 sm:gap-4">
        <div role="group" aria-label="Colour theme" class="inline-flex rounded-md border bg-card p-0.5" data-testid="theme-toggle">
          <button
            v-for="o in themeOptions"
            :key="o.value"
            type="button"
            :aria-pressed="mode === o.value"
            :aria-label="`${o.label} theme`"
            :title="`${o.label} theme`"
            class="inline-flex h-7 w-7 items-center justify-center rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :class="mode === o.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
            @click="setMode(o.value)"
          >
            <svg
              aria-hidden="true"
              class="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path :d="o.icon" />
            </svg>
          </button>
        </div>
        <template v-if="authStore.isAuthenticated">
          <span class="hidden max-w-40 truncate text-sm text-muted-foreground md:inline" :title="authStore.user?.name">{{ authStore.user?.name }}</span>
          <Button variant="ghost" size="sm" class="px-2 sm:px-3" @click="handleLogout">
            Logout
          </Button>
        </template>
      </div>
    </div>
  </header>
</template>
