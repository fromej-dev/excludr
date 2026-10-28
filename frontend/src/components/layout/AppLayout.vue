<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { onKeyStroke, useScrollLock } from '@vueuse/core'
import AppSidebar from './AppSidebar.vue'
import ExcludrWordmark from '@/components/brand/ExcludrWordmark.vue'

interface Props {
  /** Use the full content width instead of the centered column. */
  fullWidth?: boolean
}

withDefaults(defineProps<Props>(), { fullWidth: false })

const route = useRoute()
const menuOpen = ref(false)

// Close the mobile drawer on navigation and on Escape
watch(() => route.fullPath, () => (menuOpen.value = false))
onKeyStroke('Escape', () => (menuOpen.value = false))

// Don't let the page behind the open drawer scroll
const bodyLocked = useScrollLock(typeof document !== 'undefined' ? document.body : null)
watch(menuOpen, (open) => (bodyLocked.value = open))
</script>

<template>
  <div class="min-h-screen bg-background lg:flex">
    <!-- Below lg: compact top bar with a menu button that opens the sidebar as a drawer -->
    <header class="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/95 px-2 backdrop-blur supports-[backdrop-filter]:bg-background/70 lg:hidden">
      <button
        type="button"
        class="inline-flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Open menu"
        aria-controls="app-sidebar"
        :aria-expanded="menuOpen"
        data-testid="menu-button"
        @click="menuOpen = true"
      >
        <svg aria-hidden="true" class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <router-link to="/dashboard" class="text-xl"><ExcludrWordmark /></router-link>
    </header>

    <Transition
      enter-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      leave-active-class="transition-opacity duration-200"
      leave-to-class="opacity-0"
    >
      <div v-if="menuOpen" class="fixed inset-0 z-40 bg-black/50 lg:hidden" aria-hidden="true" @click="menuOpen = false" />
    </Transition>

    <AppSidebar :open="menuOpen" @close="menuOpen = false">
      <template v-if="$slots.sidebar" #default>
        <slot name="sidebar" />
      </template>
    </AppSidebar>

    <main class="min-w-0 flex-1">
      <div :class="fullWidth ? 'w-full px-4 py-4 sm:px-6' : 'mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10'">
        <slot />
      </div>
    </main>
  </div>
</template>
