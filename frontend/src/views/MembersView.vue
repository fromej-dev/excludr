<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useMembersStore } from '@/stores/members'
import { useAuthStore } from '@/stores/auth'
import { useWebSocketStore } from '@/stores/websocket'
import type { ProjectMember, ProjectRole } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Label from '@/components/ui/Label.vue'
import Select from '@/components/ui/Select.vue'
import Dialog from '@/components/ui/Dialog.vue'

const route = useRoute()
const membersStore = useMembersStore()
const authStore = useAuthStore()
const wsStore = useWebSocketStore()

const projectId = computed(() => Number(route.params.id))
const isOwner = computed(() => membersStore.isOwner)

const roleOptions = [
  { value: 'reviewer', label: 'Reviewer' },
  { value: 'viewer', label: 'Viewer' },
]

const email = ref('')
const newRole = ref<ProjectRole>('reviewer')
const adding = ref(false)
const formError = ref<string | null>(null)

const toRole = (v: string | number): ProjectRole => (v === 'viewer' ? 'viewer' : 'reviewer')

const addMember = async () => {
  if (!email.value.trim()) return
  adding.value = true
  formError.value = null
  const ok = await membersStore.addMember(projectId.value, email.value.trim(), newRole.value)
  adding.value = false
  if (ok) {
    wsStore.addNotification(`Added ${email.value.trim()}`, 'success')
    email.value = ''
  } else {
    formError.value = membersStore.error
  }
}

const changeRole = async (member: ProjectMember, value: string | number) => {
  const ok = await membersStore.changeRole(projectId.value, member.user_id, toRole(value))
  if (!ok) wsStore.addNotification(membersStore.error ?? 'Failed to change role', 'error')
}

const toRemove = ref<ProjectMember | null>(null)
const removing = ref(false)
const confirmRemove = async () => {
  if (!toRemove.value) return
  removing.value = true
  const ok = await membersStore.removeMember(projectId.value, toRemove.value.user_id)
  removing.value = false
  if (ok) {
    wsStore.addNotification(`Removed ${toRemove.value.name}`, 'success')
  } else {
    wsStore.addNotification(membersStore.error ?? 'Failed to remove member', 'error')
  }
  toRemove.value = null
}

const roleVariant = (role: ProjectRole) => (role === 'owner' ? 'default' : role === 'reviewer' ? 'secondary' : 'outline')
</script>

<template>
  <div class="space-y-6">
    <Card class="p-6 space-y-4">
      <div>
        <h2 class="text-lg font-semibold">Members</h2>
        <p class="text-sm text-muted-foreground mt-1">
          Owners manage everything, reviewers screen articles and run AI screening, viewers have
          read-only access.
        </p>
      </div>

      <p v-if="membersStore.loading && membersStore.members.length === 0" class="text-sm text-muted-foreground">
        Loading members...
      </p>
      <p v-else-if="membersStore.error && membersStore.members.length === 0" class="text-sm text-destructive">
        {{ membersStore.error }}
      </p>

      <ul class="divide-y rounded-md border" data-testid="member-list">
        <li
          v-for="m in membersStore.members"
          :key="m.user_id"
          class="flex flex-wrap items-center justify-between gap-3 p-3"
        >
          <div class="min-w-0">
            <p class="font-medium truncate">
              {{ m.name }}
              <span v-if="m.user_id === authStore.user?.id" class="text-xs text-muted-foreground">(you)</span>
            </p>
            <p class="text-sm text-muted-foreground truncate">{{ m.email }}</p>
          </div>
          <div class="flex items-center gap-2">
            <template v-if="isOwner && m.role !== 'owner'">
              <Select
                class="w-36"
                :model-value="m.role"
                :options="roleOptions"
                :aria-label="`Role for ${m.name}`"
                @update:model-value="changeRole(m, $event)"
              />
              <Button variant="outline" size="sm" @click="toRemove = m">Remove</Button>
            </template>
            <Badge v-else :variant="roleVariant(m.role)" class="capitalize">{{ m.role }}</Badge>
          </div>
        </li>
      </ul>
    </Card>

    <Card v-if="isOwner" class="p-6">
      <h3 class="font-semibold mb-1">Add a member</h3>
      <p class="text-sm text-muted-foreground mb-4">
        The person must already have an Excludr account.
      </p>
      <form class="flex flex-col gap-3 sm:flex-row sm:items-end" @submit.prevent="addMember">
        <div class="flex-1 space-y-2">
          <Label for="member-email">Email</Label>
          <Input id="member-email" v-model="email" type="email" placeholder="colleague@example.com" required />
        </div>
        <div class="space-y-2 sm:w-40">
          <Label for="member-role">Role</Label>
          <Select
            id="member-role"
            :model-value="newRole"
            :options="roleOptions"
            @update:model-value="newRole = toRole($event)"
          />
        </div>
        <Button type="submit" :disabled="adding || !email.trim()">
          {{ adding ? 'Adding...' : 'Add member' }}
        </Button>
      </form>
      <p v-if="formError" class="mt-3 text-sm text-destructive" role="alert">{{ formError }}</p>
    </Card>

    <Dialog :open="toRemove !== null" title="Remove member" @update:open="(v) => !v && (toRemove = null)">
      <div class="space-y-4">
        <p class="text-sm">
          Remove <strong>{{ toRemove?.name }}</strong> ({{ toRemove?.email }}) from this project?
        </p>
        <div class="flex justify-end gap-3">
          <Button variant="outline" @click="toRemove = null">Cancel</Button>
          <Button variant="destructive" :disabled="removing" @click="confirmRemove">Remove</Button>
        </div>
      </div>
    </Dialog>
  </div>
</template>
