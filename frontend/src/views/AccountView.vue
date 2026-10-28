<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useWebSocketStore } from '@/stores/websocket'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { AccountBilling, AccountProject, BillingUsage } from '@/types'
import AppLayout from '@/components/layout/AppLayout.vue'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Progress from '@/components/ui/Progress.vue'

const MIN_PASSWORD_LENGTH = 8

const authStore = useAuthStore()
const wsStore = useWebSocketStore()
const { get } = useApi()

// --- Profile -----------------------------------------------------------------

const name = ref('')
const savingName = ref(false)
const nameError = ref<string | null>(null)

watch(
  () => authStore.user?.name,
  (value) => (name.value = value ?? ''),
  { immediate: true }
)

const nameChanged = computed(() => name.value.trim() !== '' && name.value.trim() !== authStore.user?.name)

const saveName = async () => {
  savingName.value = true
  nameError.value = null
  try {
    await authStore.updateProfile(name.value.trim())
    wsStore.addNotification('Name updated', 'success')
  } catch (err) {
    nameError.value = getErrorMessage(err, 'Could not update your name')
  } finally {
    savingName.value = false
  }
}

// --- Email -------------------------------------------------------------------

const editingEmail = ref(false)
const newEmail = ref('')
const emailPassword = ref('')
const savingEmail = ref(false)
const emailError = ref<string | null>(null)

const startEmailChange = () => {
  newEmail.value = authStore.user?.email ?? ''
  emailPassword.value = ''
  emailError.value = null
  editingEmail.value = true
}

const saveEmail = async () => {
  savingEmail.value = true
  emailError.value = null
  try {
    await authStore.changeEmail(newEmail.value.trim(), emailPassword.value)
    editingEmail.value = false
    wsStore.addNotification('Email updated. Use it the next time you sign in.', 'success')
  } catch (err) {
    emailError.value = getErrorMessage(err, 'Could not update your email')
  } finally {
    savingEmail.value = false
    emailPassword.value = ''
  }
}

// --- Password ----------------------------------------------------------------

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const savingPassword = ref(false)
const passwordError = ref<string | null>(null)

const savePassword = async () => {
  passwordError.value = null
  if (newPassword.value.length < MIN_PASSWORD_LENGTH) {
    passwordError.value = `The new password needs at least ${MIN_PASSWORD_LENGTH} characters`
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = 'The new passwords do not match'
    return
  }
  savingPassword.value = true
  try {
    await authStore.changePassword(currentPassword.value, newPassword.value)
    currentPassword.value = newPassword.value = confirmPassword.value = ''
    wsStore.addNotification('Password changed', 'success')
  } catch (err) {
    passwordError.value = getErrorMessage(err, 'Could not change your password')
  } finally {
    savingPassword.value = false
  }
}

// --- AI usage ----------------------------------------------------------------

const usage = ref<AccountBilling | null>(null)
const usageError = ref<string | null>(null)

onMounted(async () => {
  try {
    usage.value = await get<AccountBilling>('/billing/account')
  } catch (err) {
    usageError.value = getErrorMessage(err, 'Could not load your AI usage')
  }
})

const percent = (u: BillingUsage) => (u.limit ? Math.min(100, Math.round((u.used / u.limit) * 100)) : 0)

const meterVariant = (u: BillingUsage) => {
  const p = percent(u)
  return p >= 100 ? 'destructive' : p >= 80 ? 'warning' : 'default'
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })

const memberSince = computed(() => (authStore.user?.created_at ? formatDate(authStore.user.created_at) : null))

const freeProjects = computed(() => usage.value?.projects.filter((p) => p.full_text_limit === null) ?? [])

const planBadge = (p: AccountProject) => {
  if (p.read_only) return { text: 'Expired', variant: 'destructive' as const }
  if (p.active) return { text: 'Pass', variant: 'default' as const }
  return { text: 'Free', variant: 'secondary' as const }
}

const projectUsage = (p: AccountProject) =>
  p.full_text_limit === null
    ? `${p.full_text_used.toLocaleString('en')} full texts`
    : `${p.full_text_used.toLocaleString('en')} / ${p.full_text_limit.toLocaleString('en')} full texts`
</script>

<template>
  <AppLayout>
    <div class="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 class="text-2xl font-bold tracking-tight sm:text-3xl">Account</h1>
        <p v-if="memberSince" class="mt-1 text-sm text-muted-foreground">Member since {{ memberSince }}</p>
      </div>

      <!-- Profile -->
      <Card class="space-y-6 p-6" data-testid="account-profile">
        <h2 class="font-semibold">Profile</h2>

        <form class="space-y-2" @submit.prevent="saveName">
          <Label for="account-name">Name</Label>
          <div class="flex flex-col gap-2 sm:flex-row">
            <Input id="account-name" v-model="name" autocomplete="name" required data-testid="account-name" />
            <Button type="submit" class="shrink-0" :disabled="!nameChanged || savingName" data-testid="save-name">
              {{ savingName ? 'Saving...' : 'Save' }}
            </Button>
          </div>
          <p v-if="nameError" role="alert" class="text-sm text-destructive">{{ nameError }}</p>
        </form>

        <div class="space-y-2 border-t pt-6">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="min-w-0">
              <p class="text-sm font-medium">Email</p>
              <p class="truncate text-sm text-muted-foreground" data-testid="account-email">{{ authStore.user?.email }}</p>
            </div>
            <Button v-if="!editingEmail" variant="outline" size="sm" data-testid="change-email" @click="startEmailChange">
              Change email
            </Button>
          </div>

          <form v-if="editingEmail" class="space-y-3 pt-2" @submit.prevent="saveEmail">
            <div class="space-y-2">
              <Label for="account-new-email">New email</Label>
              <Input id="account-new-email" v-model="newEmail" type="email" autocomplete="email" required />
            </div>
            <div class="space-y-2">
              <Label for="account-email-password">Current password</Label>
              <Input
                id="account-email-password"
                v-model="emailPassword"
                type="password"
                autocomplete="current-password"
                required
              />
            </div>
            <p v-if="emailError" role="alert" class="text-sm text-destructive">{{ emailError }}</p>
            <div class="flex gap-2">
              <Button type="submit" :disabled="savingEmail" data-testid="save-email">
                {{ savingEmail ? 'Saving...' : 'Save email' }}
              </Button>
              <Button type="button" variant="ghost" @click="editingEmail = false">Cancel</Button>
            </div>
          </form>
        </div>
      </Card>

      <!-- Password -->
      <Card class="p-6" data-testid="account-password">
        <form class="space-y-4" @submit.prevent="savePassword">
          <h2 class="font-semibold">Password</h2>
          <div class="space-y-2">
            <Label for="account-current-password">Current password</Label>
            <Input
              id="account-current-password"
              v-model="currentPassword"
              type="password"
              autocomplete="current-password"
              required
            />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="account-new-password">New password</Label>
              <Input
                id="account-new-password"
                v-model="newPassword"
                type="password"
                autocomplete="new-password"
                required
              />
            </div>
            <div class="space-y-2">
              <Label for="account-confirm-password">Confirm new password</Label>
              <Input
                id="account-confirm-password"
                v-model="confirmPassword"
                type="password"
                autocomplete="new-password"
                required
              />
            </div>
          </div>
          <p class="text-xs text-muted-foreground">At least {{ MIN_PASSWORD_LENGTH }} characters.</p>
          <p v-if="passwordError" role="alert" class="text-sm text-destructive">{{ passwordError }}</p>
          <Button type="submit" :disabled="savingPassword" data-testid="save-password">
            {{ savingPassword ? 'Saving...' : 'Change password' }}
          </Button>
        </form>
      </Card>

      <!-- AI usage -->
      <Card class="space-y-5 p-6" data-testid="account-usage">
        <div>
          <h2 class="font-semibold">AI screening usage</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Counted per article the AI agent has screened; re-screening the same article is free.
          </p>
        </div>

        <p v-if="usageError" role="alert" class="text-sm text-destructive">{{ usageError }}</p>
        <div v-else-if="!usage" class="h-24 animate-pulse rounded-md bg-muted" aria-busy="true">
          <span class="sr-only">Loading usage...</span>
        </div>

        <template v-else>
          <div v-if="usage.billing_enabled" class="space-y-4" data-testid="free-allowance">
            <div>
              <p class="text-sm font-medium">Free allowance</p>
              <p class="text-xs text-muted-foreground">
                Shared by
                {{ freeProjects.length === 1 ? 'your 1 project' : `your ${freeProjects.length} projects` }}
                without a review pass.
              </p>
            </div>
            <div class="space-y-1">
              <div class="flex justify-between text-sm">
                <span>Full texts</span>
                <span class="font-medium tabular-nums" data-testid="free-full-text">
                  {{ usage.free_full_text.used.toLocaleString('en') }} /
                  {{ usage.free_full_text.limit.toLocaleString('en') }}
                </span>
              </div>
              <Progress :value="percent(usage.free_full_text)" :variant="meterVariant(usage.free_full_text)" />
            </div>
            <div class="space-y-1">
              <div class="flex justify-between text-sm">
                <span>Titles and abstracts</span>
                <span class="font-medium tabular-nums">
                  {{ usage.free_title_abstract.used.toLocaleString('en') }} /
                  {{ usage.free_title_abstract.limit.toLocaleString('en') }}
                </span>
              </div>
              <Progress :value="percent(usage.free_title_abstract)" :variant="meterVariant(usage.free_title_abstract)" />
            </div>
          </div>
          <p v-else class="text-sm text-muted-foreground" data-testid="billing-disabled">
            AI screening has no usage limits here.
          </p>

          <div class="space-y-2 border-t pt-5">
            <p class="text-sm font-medium">Your projects</p>
            <p v-if="!usage.projects.length" class="text-sm text-muted-foreground">
              You don't own any projects yet.
            </p>
            <ul v-else class="divide-y rounded-md border" data-testid="usage-projects">
              <li
                v-for="project in usage.projects"
                :key="project.id"
                class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3"
              >
                <div class="min-w-0">
                  <router-link
                    :to="`/projects/${project.id}`"
                    class="block truncate text-sm font-medium hover:underline"
                  >
                    {{ project.name }}
                  </router-link>
                  <p v-if="usage.billing_enabled" class="text-xs text-muted-foreground">
                    {{ project.plan_label }}
                    <template v-if="project.expires_at && project.active">
                      · until {{ formatDate(project.expires_at) }}
                    </template>
                    <template v-else-if="project.expires_at"> · expired {{ formatDate(project.expires_at) }}</template>
                  </p>
                </div>
                <div class="flex items-center gap-3">
                  <span class="text-sm tabular-nums text-muted-foreground">{{ projectUsage(project) }}</span>
                  <Badge v-if="usage.billing_enabled" :variant="planBadge(project).variant">
                    {{ planBadge(project).text }}
                  </Badge>
                </div>
              </li>
            </ul>
            <p v-if="usage.billing_enabled" class="text-xs text-muted-foreground">
              Get a review pass for a project from its overview page.
            </p>
          </div>
        </template>
      </Card>
    </div>
  </AppLayout>
</template>
