<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const route = useRoute()

// The sign-in and sign-up pages link to each other from their own card
const onAuthPage = computed(() => route.name === 'login' || route.name === 'register')

const sections = [
  { hash: '#how-it-works', label: 'How it works' },
  { hash: '#features', label: 'Features' },
  { hash: '#pricing', label: 'Pricing' },
]
</script>

<template>
  <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
      <router-link
        to="/"
        class="flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground" aria-hidden="true">
          <svg class="h-4.5 w-4.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 5h18l-7 8.5V19l-4 2v-7.5z" />
          </svg>
        </span>
        <span class="text-xl font-bold tracking-tight">Excludr</span>
      </router-link>
      <nav class="flex items-center gap-2 sm:gap-6">
        <router-link
          v-for="section in sections"
          :key="section.hash"
          :to="{ path: '/', hash: section.hash }"
          class="hidden text-sm font-medium text-muted-foreground hover:text-foreground sm:inline"
        >
          {{ section.label }}
        </router-link>
        <template v-if="authStore.isAuthenticated">
          <router-link
            to="/dashboard"
            data-testid="home-open-app"
            class="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Open app
          </router-link>
        </template>
        <template v-else-if="!onAuthPage">
          <router-link to="/login" class="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium hover:bg-accent">
            Sign in
          </router-link>
          <router-link
            to="/register"
            class="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Get started
          </router-link>
        </template>
      </nav>
    </div>
  </header>
</template>
