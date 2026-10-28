<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useImportsStore } from '@/stores/imports'
import { useMembersStore } from '@/stores/members'
import type { ImportKind } from '@/types'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import Progress from '@/components/ui/Progress.vue'

interface Props {
  projectId: number
  /** Only owners may upload; others see the history only. */
  canUpload: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ imported: [] }>()

const importsStore = useImportsStore()
const membersStore = useMembersStore()
const { batches, state, percent, result, resultFilename, error } = storeToRefs(importsStore)

const risInput = ref<HTMLInputElement | null>(null)
const pubmedInput = ref<HTMLInputElement | null>(null)

const busy = computed(() => state.value === 'uploading' || state.value === 'processing')

const pick = (kind: ImportKind) => {
  const el = kind === 'ris' ? risInput.value : pubmedInput.value
  el?.click()
}

const onFile = async (kind: ImportKind, event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const ok = await importsStore.upload(props.projectId, kind, file)
  if (ok) emit('imported')
}

const formatLabel = (format: string): string => {
  if (format === 'ris') return 'RIS'
  if (format === 'pubmed_txt') return 'PubMed TXT'
  if (format === 'pubmed_csv') return 'PubMed CSV'
  return format
}

onMounted(() => {
  importsStore.resetUpload()
  importsStore.fetchBatches(props.projectId)
})
</script>

<template>
  <Card class="p-6 space-y-4" data-testid="import-card">
    <div>
      <h3 class="font-semibold">Import Articles</h3>
      <p class="text-sm text-muted-foreground mt-1">
        <template v-if="canUpload">
          Upload a RIS file (.ris) or a PubMed export (.txt MEDLINE or .csv). Duplicates of articles
          already in the project are skipped.
        </template>
        <template v-else-if="membersStore.role !== null">Only the project owner can import articles.</template>
      </p>
    </div>

    <div v-if="canUpload" class="flex flex-wrap gap-3">
      <Button :disabled="busy" @click="pick('ris')">Upload RIS (.ris)</Button>
      <Button variant="outline" :disabled="busy" @click="pick('pubmed')">
        Upload PubMed (.txt / .csv)
      </Button>
      <input
        ref="risInput"
        type="file"
        accept=".ris"
        class="hidden"
        data-testid="ris-input"
        @change="onFile('ris', $event)"
      />
      <input
        ref="pubmedInput"
        type="file"
        accept=".txt,.csv"
        class="hidden"
        data-testid="pubmed-input"
        @change="onFile('pubmed', $event)"
      />
    </div>

    <!-- Progress -->
    <div v-if="busy" class="space-y-2" role="status">
      <div class="flex justify-between text-sm">
        <span>
          {{ state === 'uploading' ? 'Uploading' : 'Processing' }} {{ resultFilename }}...
        </span>
        <span v-if="state === 'uploading'" class="text-muted-foreground">{{ percent }}%</span>
      </div>
      <Progress :value="state === 'processing' ? 100 : percent" />
    </div>

    <!-- Result summary -->
    <div
      v-if="state === 'done' && result"
      class="rounded-md border border-include/40 bg-include-soft text-include-soft-foreground p-4 text-sm space-y-1"
      data-testid="import-result"
    >
      <p class="font-medium">Import complete: {{ resultFilename }}</p>
      <div class="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
        <span><strong class="text-foreground">{{ result.articles_created ?? 0 }}</strong> imported</span>
        <span><strong class="text-foreground">{{ result.duplicates ?? 0 }}</strong> duplicates</span>
        <span v-if="result.articles_updated">
          <strong class="text-foreground">{{ result.articles_updated }}</strong> updated
        </span>
        <span v-if="result.abstracts_fetched">
          <strong class="text-foreground">{{ result.abstracts_fetched }}</strong> abstracts fetched
        </span>
      </div>
    </div>

    <div
      v-if="state === 'error' && error"
      class="rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
      role="alert"
    >
      {{ error }}
    </div>

    <!-- History -->
    <div v-if="batches.length > 0" class="space-y-2">
      <h4 class="text-sm font-semibold">Import history</h4>
      <div class="overflow-x-auto rounded-md border">
        <table class="w-full text-sm">
          <thead class="bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-medium">File</th>
              <th class="px-3 py-2 font-medium">Format</th>
              <th class="px-3 py-2 font-medium text-right">Records</th>
              <th class="px-3 py-2 font-medium text-right">Imported</th>
              <th class="px-3 py-2 font-medium text-right">Duplicates</th>
              <th class="px-3 py-2 font-medium">Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in batches" :key="b.id" class="border-t">
              <td class="px-3 py-2 break-all">{{ b.filename }}</td>
              <td class="px-3 py-2"><Badge variant="outline">{{ formatLabel(b.format) }}</Badge></td>
              <td class="px-3 py-2 text-right">{{ b.records_found }}</td>
              <td class="px-3 py-2 text-right">{{ b.imported }}</td>
              <td class="px-3 py-2 text-right">{{ b.duplicates }}</td>
              <td class="px-3 py-2 whitespace-nowrap text-muted-foreground">
                {{ new Date(b.created_at).toLocaleString() }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <p v-else class="text-sm text-muted-foreground">No imports yet.</p>
  </Card>
</template>
