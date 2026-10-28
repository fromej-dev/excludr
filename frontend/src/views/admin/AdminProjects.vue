<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDebounceFn } from '@vueuse/core'
import { useAdminStore } from '@/stores/admin'
import { getErrorMessage } from '@/utils/errors'
import type { AdminPage, AdminProject, AdminProjectState } from '@/types'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import Pager from '@/components/admin/Pager.vue'
import ProjectTable from '@/components/admin/ProjectTable.vue'
import PlanDialog from '@/components/admin/PlanDialog.vue'

const PAGE_SIZE = 25
const STATES = ['free', 'active', 'expiring', 'expired']
const route = useRoute()
const router = useRouter()
const admin = useAdminStore()

const initialState = String(route.query.state ?? '')
const search = ref<string | number>('')
const state = ref<string | number>(STATES.includes(initialState) ? initialState : '')
const page = ref(1)
const result = ref<AdminPage<AdminProject> | null>(null)
const error = ref<string | null>(null)
const managing = ref<AdminProject | null>(null)

const stateOptions = [
  { value: '', label: 'All plans' },
  { value: 'free', label: 'Free (no pass)' },
  { value: 'active', label: 'Active pass' },
  { value: 'expiring', label: 'Ending within 30 days' },
  { value: 'expired', label: 'Expired (read-only)' },
]

const load = async () => {
  try {
    error.value = null
    result.value = await admin.projects({
      search: String(search.value).trim(),
      state: state.value as AdminProjectState | '',
      page: page.value,
      page_size: PAGE_SIZE,
    })
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Could not load projects')
  }
}

const reload = useDebounceFn(() => {
  page.value = 1
  void load()
}, 300)

watch(search, reload)
watch(state, (value) => {
  router.replace({ query: value ? { state: String(value) } : {} })
  page.value = 1
  void load()
})
watch(page, load)
onMounted(load)

const onSaved = () => {
  managing.value = null
  void load()
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap gap-3">
      <Input v-model="search" type="search" placeholder="Search by project or owner e-mail" class="max-w-sm" />
      <Select v-model="state" :options="stateOptions" class="max-w-xs" aria-label="Plan state" />
    </div>
    <p v-if="error" role="alert" class="rounded-md bg-destructive/15 p-3 text-sm text-destructive">{{ error }}</p>
    <div v-if="result" class="space-y-3">
      <ProjectTable :projects="result.items" show-owner @manage="managing = $event" />
      <Pager v-model:page="page" :page-size="PAGE_SIZE" :total="result.total" />
    </div>
    <PlanDialog :project="managing" @close="managing = null" @saved="onSaved" />
  </div>
</template>
