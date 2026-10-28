<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import { useAuthStore } from '@/stores/auth'
import { useWebSocketStore } from '@/stores/websocket'
import { formatPrice } from '@/stores/billing'
import { formatCount, formatDate } from '@/utils/format'
import { getErrorMessage } from '@/utils/errors'
import type { AdminProject, AdminUserDetail } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import ProjectTable from '@/components/admin/ProjectTable.vue'
import PlanDialog from '@/components/admin/PlanDialog.vue'

const route = useRoute()
const admin = useAdminStore()
const authStore = useAuthStore()
const wsStore = useWebSocketStore()

const userId = computed(() => Number(route.params.userId))
const user = ref<AdminUserDetail | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)
const managing = ref<AdminProject | null>(null)
const isSelf = computed(() => authStore.user?.id === userId.value)

const load = async () => {
  try {
    error.value = null
    user.value = await admin.user(userId.value)
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not load the user')
  }
}
watch(userId, load, { immediate: true })

const change = async (changes: { is_active?: boolean; is_superuser?: boolean }, confirmText: string, done: string) => {
  if (!window.confirm(confirmText)) return
  busy.value = true
  try {
    user.value = await admin.updateUser(userId.value, changes)
    wsStore.addNotification(done, 'success')
  } catch (err: unknown) {
    wsStore.addNotification(getErrorMessage(err, 'Could not update the user'), 'error')
  } finally {
    busy.value = false
  }
}

const toggleActive = () => {
  if (!user.value) return
  const deactivate = user.value.is_active
  void change(
    { is_active: !deactivate },
    deactivate
      ? `Deactivate ${user.value.email}? They are signed out and cannot log in.`
      : `Reactivate ${user.value.email}?`,
    deactivate ? 'Account deactivated' : 'Account reactivated'
  )
}

const toggleAdmin = () => {
  if (!user.value) return
  const grant = !user.value.is_superuser
  void change(
    { is_superuser: grant },
    grant
      ? `Give ${user.value.email} admin rights? They will see all users, projects and payments.`
      : `Remove admin rights from ${user.value.email}?`,
    grant ? 'Admin rights granted' : 'Admin rights removed'
  )
}

const onSaved = () => {
  managing.value = null
  void load()
}
</script>

<template>
  <div class="space-y-6">
    <router-link :to="{ name: 'admin-users' }" class="text-sm text-muted-foreground hover:text-foreground">
      ← All users
    </router-link>
    <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{{ error }}</p>
    <template v-if="user">
      <Card class="p-6">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="text-2xl font-bold">{{ user.name }}</h2>
              <Badge v-if="user.is_superuser" variant="secondary">Admin</Badge>
              <Badge v-if="!user.is_active" variant="destructive" data-testid="user-deactivated">Deactivated</Badge>
            </div>
            <p class="text-muted-foreground">{{ user.email }}</p>
            <p class="mt-2 text-sm text-muted-foreground">
              Joined {{ formatDate(user.created_at) }} · {{ formatCount(user.project_count) }} projects ·
              {{ formatCount(user.ai_fulltext_used) }} AI full texts · paid
              {{ formatPrice(user.payments_total_cents) }}
            </p>
          </div>
          <div v-if="!isSelf" class="flex gap-2">
            <Button size="sm" variant="outline" :disabled="busy" data-testid="toggle-admin" @click="toggleAdmin">
              {{ user.is_superuser ? 'Remove admin rights' : 'Make admin' }}
            </Button>
            <Button
              size="sm"
              :variant="user.is_active ? 'destructive' : 'default'"
              :disabled="busy"
              data-testid="toggle-active"
              @click="toggleActive"
            >
              {{ user.is_active ? 'Deactivate' : 'Reactivate' }}
            </Button>
          </div>
          <p v-else class="text-xs text-muted-foreground">This is you.</p>
        </div>
      </Card>

      <div class="space-y-3">
        <h3 class="font-semibold">Projects owned</h3>
        <ProjectTable :projects="user.projects" @manage="managing = $event" />
      </div>
    </template>
    <PlanDialog :project="managing" @close="managing = null" @saved="onSaved" />
  </div>
</template>
