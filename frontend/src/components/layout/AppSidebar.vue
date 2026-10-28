<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTheme, type ThemeMode } from '@/composables/useTheme'

interface Props {
  /** Drawer state below lg; the sidebar is always shown from lg up. */
  open?: boolean
}

withDefaults(defineProps<Props>(), { open: false })
const emit = defineEmits<{ close: [] }>()

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const { mode, setMode } = useTheme()

// Lucide-style 24x24 stroke icon paths.
const icons = {
  projects: 'M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z',
  admin: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  close: 'M18 6 6 18M6 6l12 12',
}

const themeOptions: { value: ThemeMode; label: string; icon: string }[] = [
  {
    value: 'light',
    label: 'Light',
    icon: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41',
  },
  { value: 'system', label: 'System', icon: 'M3 4h18a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 21h8M12 17v4' },
  { value: 'dark', label: 'Dark', icon: 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z' },
]

const links = computed(() => {
  const items = [{ key: 'projects', label: 'Projects', to: '/dashboard', icon: icons.projects, active: route.name === 'dashboard' }]
  if (authStore.user?.is_superuser) {
    items.push({ key: 'admin', label: 'Admin', to: '/admin', icon: icons.admin, active: route.path.startsWith('/admin') })
  }
  return items
})

const initials = computed(() => {
  const source = authStore.user?.name?.trim() || authStore.user?.email || ''
  const parts = source.split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase() || '?'
})

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <aside
    id="app-sidebar"
    aria-label="Main"
    class="fixed inset-y-0 left-0 z-50 flex h-dvh w-72 max-w-[85vw] flex-col border-r bg-card shadow-xl transition-[transform,visibility] duration-200 ease-out lg:visible lg:sticky lg:top-0 lg:z-auto lg:h-screen lg:w-64 lg:translate-x-0 lg:shadow-none"
    :class="open ? 'visible translate-x-0' : 'invisible -translate-x-full'"
    data-testid="app-sidebar"
  >
    <div class="flex h-14 shrink-0 items-center justify-between gap-2 px-4 lg:h-16">
      <router-link
        to="/dashboard"
        class="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground" aria-hidden="true">
          <svg class="h-4.5 w-4.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 5h18l-7 8.5V19l-4 2v-7.5z" />
          </svg>
        </span>
        <span class="text-lg font-bold tracking-tight">Excludr</span>
      </router-link>
      <button
        type="button"
        class="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
        aria-label="Close menu"
        @click="emit('close')"
      >
        <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path :d="icons.close" />
        </svg>
      </button>
    </div>

    <div class="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-3 py-3">
      <nav v-if="authStore.isAuthenticated" aria-label="Main navigation">
        <ul class="space-y-0.5">
          <li v-for="link in links" :key="link.key">
            <router-link
              :to="link.to"
              :aria-current="link.active ? 'page' : undefined"
              :data-testid="link.key === 'admin' ? 'admin-link' : 'projects-link'"
              class="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :class="link.active ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'"
            >
              <svg aria-hidden="true" class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path :d="link.icon" />
              </svg>
              {{ link.label }}
            </router-link>
          </li>
        </ul>
      </nav>

      <!-- Contextual navigation (e.g. the current project's sections) -->
      <div v-if="$slots.default" class="border-t pt-5">
        <slot />
      </div>
    </div>

    <div class="shrink-0 space-y-3 border-t p-3">
      <div role="group" aria-label="Colour theme" class="grid grid-cols-3 rounded-md border bg-background p-0.5" data-testid="theme-toggle">
        <button
          v-for="o in themeOptions"
          :key="o.value"
          type="button"
          :aria-pressed="mode === o.value"
          :aria-label="`${o.label} theme`"
          :title="`${o.label} theme`"
          class="inline-flex h-7 items-center justify-center rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :class="mode === o.value ? 'bg-accent text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
          @click="setMode(o.value)"
        >
          <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path :d="o.icon" />
          </svg>
        </button>
      </div>

      <div v-if="authStore.isAuthenticated" class="flex items-center gap-3 px-1">
        <span
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-secondary-foreground"
          aria-hidden="true"
          >{{ initials }}</span
        >
        <div class="min-w-0 flex-1 leading-tight">
          <p class="truncate text-sm font-medium" :title="authStore.user?.name">{{ authStore.user?.name }}</p>
          <p class="truncate text-xs text-muted-foreground" :title="authStore.user?.email">{{ authStore.user?.email }}</p>
        </div>
        <button
          type="button"
          class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Log out"
          title="Log out"
          data-testid="logout"
          @click="handleLogout"
        >
          <svg aria-hidden="true" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path :d="icons.logout" />
          </svg>
        </button>
      </div>
    </div>
  </aside>
</template>
