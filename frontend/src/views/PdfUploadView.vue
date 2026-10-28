<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useApi } from '@/composables/useApi'
import { useMembersStore } from '@/stores/members'
import { useWebSocketStore } from '@/stores/websocket'
import { getErrorMessage } from '@/utils/errors'
import Card from '@/components/ui/Card.vue'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import Progress from '@/components/ui/Progress.vue'
import PdfArticlePicker from '@/components/articles/PdfArticlePicker.vue'
import type {
  PdfArticleChoice as ArticleChoice,
  PdfAttachResult,
  PdfBulkConfirmResponse,
  PdfMatchCandidate,
  PdfMatchConfidence,
  PdfMatchResult,
} from '@/types'

/** Files per match request (the server accepts up to 25). */
const CHUNK = 5

interface Row {
  key: number
  filename: string
  uploadId: string | null
  error: string | null
  textExtracted: boolean
  candidates: PdfMatchCandidate[]
  article: ArticleChoice | null
  method: string | null
  confidence: PdfMatchConfidence | null
  attach: boolean
  replace: boolean
  picking: boolean
  result: PdfAttachResult | null
}

const route = useRoute()
const { post } = useApi()
const wsStore = useWebSocketStore()
const { isOwner } = storeToRefs(useMembersStore())
const projectId = computed(() => Number(route.params.id))

const rows = ref<Row[]>([])
const total = ref(0)
const matching = ref(false)
const confirming = ref(false)
const confirmed = ref(false)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
let nextKey = 0

const METHOD_LABELS: Record<string, string> = {
  article_id_filename: 'Excludr file name',
  doi_metadata: 'DOI in PDF metadata',
  doi_filename: 'DOI in file name',
  doi_text: 'DOI on first page',
  pmid_filename: 'PMID in file name',
  pmcid_filename: 'PMCID in file name',
  pmid_text: 'PMID on first page',
  pmcid_text: 'PMCID on first page',
  title_text: 'Title on first page',
  title_metadata: 'Title in PDF metadata',
  title_filename: 'Title in file name',
}

const toRow = (r: PdfMatchResult): Row => {
  const m = r.match
  return {
    key: nextKey++,
    filename: r.filename,
    uploadId: r.upload_id,
    error: r.error,
    textExtracted: r.text_extracted,
    candidates: r.candidates,
    article: m,
    method: m?.method ?? null,
    confidence: m?.confidence ?? null,
    // Only confident matches to articles without a full text are pre-selected
    attach: !!m && m.confidence === 'high' && !m.has_full_text,
    replace: false,
    picking: false,
    result: null,
  }
}

const addFiles = async (list: FileList | File[] | null | undefined) => {
  const files = Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith('.pdf'))
  const skipped = (list?.length ?? 0) - files.length
  if (skipped > 0) wsStore.addNotification(`${skipped} non-PDF file(s) ignored`, 'info')
  if (files.length === 0) return
  if (confirmed.value) reset()

  matching.value = true
  total.value += files.length
  for (let i = 0; i < files.length; i += CHUNK) {
    const chunk = files.slice(i, i + CHUNK)
    const form = new FormData()
    chunk.forEach((f) => form.append('files', f))
    try {
      const results = await post<PdfMatchResult[]>(
        `/projects/${projectId.value}/articles/fulltext/bulk/match`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      rows.value.push(...results.map(toRow))
    } catch (err: unknown) {
      const message = getErrorMessage(err, 'Upload failed')
      rows.value.push(
        ...chunk.map((f) =>
          toRow({ upload_id: null, filename: f.name, error: message, text_extracted: false, match: null, candidates: [] })
        )
      )
    }
  }
  matching.value = false
}

const onPick = (event: Event) => {
  const el = event.target as HTMLInputElement
  void addFiles(el.files)
  el.value = ''
}

const onDrop = (event: DragEvent) => {
  dragging.value = false
  void addFiles(event.dataTransfer?.files)
}

const choose = (row: Row, choice: ArticleChoice) => {
  const candidate = row.candidates.find((c) => c.article_id === choice.article_id)
  row.article = choice
  row.method = candidate?.method ?? 'manual'
  row.confidence = candidate?.confidence ?? null
  row.attach = true
  row.replace = false
  row.picking = false
}

const staged = computed(() => rows.value.filter((r) => r.uploadId))
const selected = computed(() => staged.value.filter((r) => r.attach && r.article))

/** Article ids chosen for more than one selected file. */
const duplicates = computed(() => {
  const seen = new Map<number, number>()
  for (const r of selected.value) seen.set(r.article!.article_id, (seen.get(r.article!.article_id) ?? 0) + 1)
  return new Set([...seen].filter(([, n]) => n > 1).map(([id]) => id))
})

const counts = computed(() => ({
  matched: staged.value.filter((r) => r.confidence === 'high').length,
  check: staged.value.filter((r) => r.article && r.confidence !== 'high').length,
  unmatched: staged.value.filter((r) => !r.article).length,
  errors: rows.value.filter((r) => r.error).length,
}))

const canConfirm = computed(
  () => !matching.value && !confirming.value && selected.value.length > 0 && duplicates.value.size === 0
)

const confirm = async () => {
  confirming.value = true
  try {
    const attachRows = selected.value
    const res = await post<PdfBulkConfirmResponse>(`/projects/${projectId.value}/articles/fulltext/bulk/confirm`, {
      attach: attachRows.map((r) => ({
        upload_id: r.uploadId!,
        article_id: r.article!.article_id,
        replace: r.replace,
      })),
      discard: staged.value.filter((r) => !attachRows.includes(r)).map((r) => r.uploadId!),
    })
    const byUpload = new Map(res.results.map((r) => [r.upload_id, r]))
    for (const row of rows.value) {
      if (row.uploadId) row.result = byUpload.get(row.uploadId) ?? null
    }
    confirmed.value = true
    wsStore.addNotification(`${res.attached} PDF(s) attached`, res.attached > 0 ? 'success' : 'info')
  } catch (err: unknown) {
    wsStore.addNotification(getErrorMessage(err, 'Attaching the PDFs failed'), 'error')
  } finally {
    confirming.value = false
  }
}

/** Drop staged files that were never confirmed (best effort; the server also expires them). */
const discardAll = () => {
  const ids = staged.value.map((r) => r.uploadId!)
  if (confirmed.value || ids.length === 0) return
  void post(`/projects/${projectId.value}/articles/fulltext/bulk/confirm`, { attach: [], discard: ids }).catch(
    () => undefined
  )
}

const reset = () => {
  discardAll()
  rows.value = []
  total.value = 0
  confirmed.value = false
}

onBeforeUnmount(discardAll)

const statusOf = (row: Row): { label: string; variant: 'include' | 'uncertain' | 'exclude' | 'outline' | 'secondary' } => {
  if (row.result) {
    if (row.result.status === 'attached') return { label: 'Attached', variant: 'include' }
    if (row.result.status === 'skipped') return { label: 'Skipped', variant: 'secondary' }
    return { label: 'Failed', variant: 'exclude' }
  }
  if (row.error) return { label: 'Rejected', variant: 'exclude' }
  if (!row.article) return { label: 'No match', variant: 'outline' }
  if (row.method === 'manual') return { label: 'Chosen', variant: 'secondary' }
  if (row.confidence === 'high') return { label: 'Matched', variant: 'include' }
  return { label: 'Check', variant: 'uncertain' }
}

const articleLabel = (a: ArticleChoice) => `${a.title ?? 'Untitled'}${a.year ? ` (${a.year})` : ''}`
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <router-link
          :to="{ name: 'project-articles', params: { id: projectId } }"
          class="text-sm text-muted-foreground hover:underline"
        >
          &larr; Articles
        </router-link>
        <h2 class="text-xl font-semibold">Upload full-text PDFs</h2>
        <p class="text-sm text-muted-foreground">
          Drop many PDFs at once. Each file is matched to an article by its DOI, PMID or PMCID, or by its title.
          Nothing is attached until you confirm.
        </p>
      </div>
    </div>

    <p v-if="!isOwner" class="rounded-md border p-3 text-sm text-muted-foreground" data-testid="pdf-upload-owner-only">
      Only project owners can upload full texts.
    </p>

    <template v-else>
      <Card
        class="border-2 border-dashed p-8 text-center transition-colors"
        :class="dragging ? 'border-primary bg-accent/40' : ''"
        data-testid="pdf-dropzone"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <p class="font-medium">Drag PDFs here</p>
        <p class="mt-1 text-sm text-muted-foreground">or</p>
        <Button class="mt-2" variant="outline" size="sm" :disabled="matching || confirming" @click="fileInput?.click()">
          Choose files
        </Button>
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,application/pdf"
          multiple
          class="hidden"
          data-testid="pdf-file-input"
          @change="onPick"
        />
        <p class="mt-3 text-xs text-muted-foreground">
          Tip: file names with a DOI or PMID (e.g. <code>10.1016_j.jad.2020.01.002.pdf</code>) or reference-manager
          names (<code>Author - Year - Title.pdf</code>) match best. Scanned PDFs without text can only match by file
          name.
        </p>
      </Card>

      <div v-if="matching" class="space-y-1" data-testid="pdf-matching-progress">
        <Progress :value="total ? Math.round((rows.length / total) * 100) : 0" />
        <p class="text-xs text-muted-foreground">Matching {{ rows.length }} / {{ total }} files...</p>
      </div>

      <Card v-if="rows.length > 0" class="p-0" data-testid="pdf-review">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <p class="text-sm">
            <strong>{{ counts.matched }}</strong> matched
            <span class="text-muted-foreground"> - </span><strong>{{ counts.check }}</strong> to check
            <span class="text-muted-foreground"> - </span><strong>{{ counts.unmatched }}</strong> unmatched
            <template v-if="counts.errors > 0">
              <span class="text-muted-foreground"> - </span><strong>{{ counts.errors }}</strong> rejected
            </template>
          </p>
          <div class="flex gap-2">
            <Button v-if="confirmed" size="sm" variant="outline" @click="reset">Upload more</Button>
            <template v-else>
              <Button size="sm" variant="ghost" :disabled="matching || confirming" @click="reset">Clear</Button>
              <Button size="sm" :disabled="!canConfirm" data-testid="pdf-confirm" @click="confirm">
                {{ confirming ? 'Attaching...' : `Attach ${selected.length} PDF${selected.length === 1 ? '' : 's'}` }}
              </Button>
            </template>
          </div>
        </div>
        <p v-if="duplicates.size > 0" role="alert" class="border-b p-3 text-sm text-destructive">
          Several files are set to the same article. Untick or change all but one.
        </p>

        <ul class="divide-y">
          <li
            v-for="row in rows"
            :key="row.key"
            class="grid gap-2 p-4 sm:grid-cols-[auto_1fr_auto] sm:items-start"
            data-testid="pdf-row"
          >
            <input
              type="checkbox"
              class="mt-1 h-4 w-4"
              :aria-label="`Attach ${row.filename}`"
              :checked="row.attach && !!row.article"
              :disabled="!row.article || !row.uploadId || confirmed"
              @change="row.attach = ($event.target as HTMLInputElement).checked"
            />
            <div class="min-w-0 space-y-1">
              <p class="truncate font-mono text-xs text-muted-foreground" :title="row.filename">{{ row.filename }}</p>
              <p v-if="row.error" class="text-sm text-destructive">{{ row.error }}</p>
              <template v-else>
                <p v-if="row.article" class="text-sm font-medium" data-testid="pdf-row-article">
                  {{ articleLabel(row.article) }}
                </p>
                <p v-else class="text-sm text-muted-foreground">No matching article found.</p>
                <p class="text-xs text-muted-foreground">
                  <template v-if="row.method && row.method !== 'manual'">{{ METHOD_LABELS[row.method] ?? row.method }}</template>
                  <template v-if="!row.textExtracted"> - no text in PDF (scanned?)</template>
                </p>
                <p
                  v-if="row.article && duplicates.has(row.article.article_id) && row.attach"
                  class="text-xs text-destructive"
                >
                  Another file is set to this article.
                </p>
                <label
                  v-if="row.article?.has_full_text && !confirmed"
                  class="flex items-center gap-2 text-xs text-muted-foreground"
                >
                  <input v-model="row.replace" type="checkbox" class="h-3 w-3" />
                  Article already has a full text; replace it
                </label>
                <p v-if="row.result?.detail" class="text-xs text-muted-foreground">{{ row.result.detail }}</p>
                <PdfArticlePicker
                  v-if="row.picking"
                  :project-id="projectId"
                  :candidates="row.candidates"
                  @pick="choose(row, $event)"
                  @cancel="row.picking = false"
                />
              </template>
            </div>
            <div class="flex items-center gap-2 sm:justify-end">
              <Badge :variant="statusOf(row).variant" :glyph="false">{{ statusOf(row).label }}</Badge>
              <Button
                v-if="row.uploadId && !confirmed && !row.picking"
                size="sm"
                variant="ghost"
                @click="row.picking = true"
              >
                {{ row.article ? 'Change' : 'Choose article' }}
              </Button>
            </div>
          </li>
        </ul>
      </Card>
    </template>
  </div>
</template>
