<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Card from '@/components/ui/Card.vue'
import PublicHeader from '@/components/layout/PublicHeader.vue'

const router = useRouter()
const route = useRoute()

// Only follow in-app redirects, never an absolute URL
const redirectTarget = () => {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')
    ? target
    : '/dashboard'
}
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const errorMessage = ref('')

const handleSubmit = async () => {
  errorMessage.value = ''

  const success = await authStore.login({
    username: email.value,
    password: password.value,
  })

  if (success) {
    router.push(redirectTarget())
  } else {
    errorMessage.value = authStore.error || 'Login failed'
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <PublicHeader />
    <main class="flex flex-1 items-center justify-center px-4 py-12">
      <Card class="w-full max-w-md p-8">
        <div class="mb-8 text-center">
          <h1 class="text-3xl font-bold">Sign in</h1>
          <p class="mt-2 text-muted-foreground">Welcome back to Excludr</p>
        </div>

        <form @submit.prevent="handleSubmit" class="space-y-4">
          <div class="space-y-2">
            <Label for="email">Email</Label>
            <Input
              id="email"
              v-model="email"
              type="email"
              placeholder="you@example.com"
              required
            />
          </div>

          <div class="space-y-2">
            <Label for="password">Password</Label>
            <Input
              id="password"
              v-model="password"
              type="password"
              placeholder="Enter your password"
              required
            />
          </div>

          <div v-if="errorMessage" role="alert" data-testid="auth-error" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
            {{ errorMessage }}
          </div>

          <Button type="submit" class="w-full" :disabled="authStore.loading">
            {{ authStore.loading ? 'Signing in...' : 'Sign in' }}
          </Button>
        </form>

        <div class="mt-4 text-center text-sm">
          <span class="text-muted-foreground">Don't have an account?</span>
          <router-link to="/register" class="ml-1 font-medium text-primary hover:underline">
            Sign up
          </router-link>
        </div>
      </Card>
    </main>
  </div>
</template>
