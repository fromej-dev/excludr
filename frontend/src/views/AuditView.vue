<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuditStore } from '@/stores/audit'
import { useMembersStore } from '@/stores/members'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'

const route = useRoute()
const auditStore = useAuditStore()
const membersStore = useMembersStore()

const projectId = computed(() => Number(route.params.id))
const isOwner = computed(() => membersStore.isOwner)

const load = (page = 1) => auditStore.fetchEvents(projectId.value, page)

onMounted(() => {
  if (isOwner.value) load()
})
watch(isOwner, (owner, was) => {
  if (owner && !was) load()
})

const memberName = (userId: number | null): string => {
  if (userId === null) return 'System'
  return membersStore.members.find((m) => m.user_id === userId)?.name ?? `User #${userId}`
}

const summarize = (details: Record<string, unknown> | null): string =>
  details
    ? Object.entries(details)
        .filter(([, v]) => v !== null && v !== undefined)
        .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
        .join(', ')
    : ''
</script>

<template>
  <div class="space-y-4">
    <Card v-if="!isOwner" class="p-6 text-sm text-muted-foreground">
      Only the project owner can view the audit log.
    </Card>

    <Card v-else class="p-6 space-y-4">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold">Audit log</h2>
          <p class="text-sm text-muted-foreground">Append-only history of project activity, newest first.</p>
        </div>
        <Badge variant="secondary">{{ auditStore.totalItems }} events</Badge>
      </div>

      <p v-if="auditStore.error" class="text-sm text-destructive" role="alert">{{ auditStore.error }}</p>
      <p v-else-if="auditStore.loading && auditStore.events.length === 0" class="text-sm text-muted-foreground">
        Loading...
      </p>
      <p v-else-if="auditStore.events.length === 0" class="text-sm text-muted-foreground">No events yet.</p>

      <div v-else class="overflow-x-auto rounded-md border">
        <table class="w-full text-sm" data-testid="audit-table">
          <thead class="bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-medium whitespace-nowrap">When</th>
              <th class="px-3 py-2 font-medium">User</th>
              <th class="px-3 py-2 font-medium">Action</th>
              <th class="px-3 py-2 font-medium">Entity</th>
              <th class="px-3 py-2 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in auditStore.events" :key="e.id" class="border-t align-top">
              <td class="px-3 py-2 whitespace-nowrap text-muted-foreground">
                {{ new Date(e.created_at).toLocaleString() }}
              </td>
              <td class="px-3 py-2 whitespace-nowrap">{{ memberName(e.user_id) }}</td>
              <td class="px-3 py-2"><Badge variant="outline" class="font-mono">{{ e.action }}</Badge></td>
              <td class="px-3 py-2 whitespace-nowrap text-muted-foreground">
                {{ e.entity_type }}<span v-if="e.entity_id !== null"> #{{ e.entity_id }}</span>
              </td>
              <td class="px-3 py-2 text-xs text-muted-foreground break-words">{{ summarize(e.details) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="auditStore.totalPages > 1" class="flex items-center justify-between">
        <Button variant="outline" size="sm" :disabled="auditStore.page <= 1 || auditStore.loading" @click="load(auditStore.page - 1)">
          Previous
        </Button>
        <span class="text-sm text-muted-foreground">Page {{ auditStore.page }} of {{ auditStore.totalPages }}</span>
        <Button
          variant="outline"
          size="sm"
          :disabled="auditStore.page >= auditStore.totalPages || auditStore.loading"
          @click="load(auditStore.page + 1)"
        >
          Next
        </Button>
      </div>
    </Card>
  </div>
</template>
