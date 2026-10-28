<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useAdminStore } from '@/stores/admin'
import { formatCount, formatDate } from '@/utils/format'
import { getErrorMessage } from '@/utils/errors'
import type { AdminPage, AdminUser } from '@/types'
import Input from '@/components/ui/Input.vue'
import Badge from '@/components/ui/Badge.vue'
import Pager from '@/components/admin/Pager.vue'

const PAGE_SIZE = 25
const admin = useAdminStore()

const search = ref<string | number>('')
const page = ref(1)
const result = ref<AdminPage<AdminUser> | null>(null)
const error = ref<string | null>(null)

const load = async () => {
  try {
    error.value = null
    result.value = await admin.users({ search: String(search.value).trim(), page: page.value, page_size: PAGE_SIZE })
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not load users')
  }
}

const reload = useDebounceFn(() => {
  page.value = 1
  void load()
}, 300)

watch(search, reload)
watch(page, load)
onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <Input v-model="search" type="search" placeholder="Search by name or e-mail" class="max-w-sm" />
    <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{{ error }}</p>
    <div v-if="result" class="space-y-3">
      <div class="overflow-x-auto rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-medium">User</th>
              <th class="px-3 py-2 text-right font-medium">Projects</th>
              <th class="px-3 py-2 text-right font-medium">Active passes</th>
              <th class="px-3 py-2 text-right font-medium">AI full texts</th>
              <th class="px-3 py-2 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in result.items" :key="u.id" class="border-t" data-testid="admin-user-row">
              <td class="px-3 py-2">
                <router-link
                  :to="{ name: 'admin-user', params: { userId: u.id } }"
                  class="font-medium hover:text-primary hover:underline"
                >
                  {{ u.name }}
                </router-link>
                <Badge v-if="u.is_superuser" variant="secondary" class="ml-2">Admin</Badge>
                <Badge v-if="!u.is_active" variant="destructive" class="ml-2">Deactivated</Badge>
                <div class="text-xs text-muted-foreground">{{ u.email }}</div>
              </td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(u.project_count) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(u.active_passes) }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(u.ai_fulltext_used) }}</td>
              <td class="px-3 py-2">{{ formatDate(u.created_at) }}</td>
            </tr>
            <tr v-if="!result.items.length">
              <td colspan="5" class="px-3 py-6 text-center text-muted-foreground">No users found</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager v-model:page="page" :page-size="PAGE_SIZE" :total="result.total" />
    </div>
  </div>
</template>
