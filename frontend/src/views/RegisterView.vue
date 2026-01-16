<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Card from '@/components/ui/Card.vue'

const router = useRouter()
const authStore = useAuthStore()

const name = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMessage = ref('')

const handleSubmit = async () => {
  errorMessage.value = ''

  if (password.value !== confirmPassword.value) {
    errorMessage.value = 'Passwords do not match'
    return
  }

  const success = await authStore.register({
    name: name.value,
    email: email.value,
    password: password.value,
  })

  if (success) {
    router.push('/')
  } else {
    errorMessage.value = authStore.error || 'Registration failed'
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-background">
    <Card class="w-full max-w-md p-8">
      <div class="mb-8 text-center">
        <h1 class="text-3xl font-bold">Excludr</h1>
        <p class="mt-2 text-muted-foreground">Create your account</p>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div class="space-y-2">
          <Label for="name">Name</Label>
          <Input
            id="name"
            v-model="name"
            type="text"
            placeholder="Your name"
            required
          />
        </div>

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
            placeholder="Create a password"
            required
          />
        </div>

        <div class="space-y-2">
          <Label for="confirm-password">Confirm Password</Label>
          <Input
            id="confirm-password"
            v-model="confirmPassword"
            type="password"
            placeholder="Confirm your password"
            required
          />
        </div>

        <div v-if="errorMessage" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
          {{ errorMessage }}
        </div>

        <Button type="submit" class="w-full" :disabled="authStore.loading">
          {{ authStore.loading ? 'Creating account...' : 'Sign up' }}
        </Button>
      </form>

      <div class="mt-4 text-center text-sm">
        <span class="text-muted-foreground">Already have an account?</span>
        <router-link to="/login" class="ml-1 font-medium text-primary hover:underline">
          Sign in
        </router-link>
      </div>
    </Card>
  </div>
</template>
