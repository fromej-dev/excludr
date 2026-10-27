<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { Article, FullTextUploadResponse, FullTextRetrievalResult } from '@/types'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Progress from '@/components/ui/Progress.vue'

interface Props {
  article: Article
  /** Owner only: show the PDF upload control. */
  canUpload?: boolean
  /** Scroll height of the text viewer. */
  heightClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  canUpload: false,
  heightClass: 'max-h-[70vh]',
})
const emit = defineEmits<{ uploaded: [] }>()

const { api, post } = useApi()

const input = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const percent = ref(0)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

const text = computed(() => props.article.full_text_content?.trim() ?? '')
const hasPdf = computed(() => !!props.article.full_text_path)

// --- PDF viewer: fetched through the authenticated API and shown from an object URL
type ViewTab = 'pdf' | 'text'
const tab = ref<ViewTab>('pdf')
const pdfUrl = ref<string | null>(null)
const pdfLoading = ref(false)
const pdfMissing = ref(false)
const pdfError = ref<string | null>(null)

const revokePdf = () => {
  if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value)
  pdfUrl.value = null
}

const loadPdf = async () => {
  revokePdf()
  pdfMissing.value = false
  pdfError.value = null
  if (!hasPdf.value) {
    pdfMissing.value = true
    return
  }
  pdfLoading.value = true
  const { project_id, id } = props.article
  try {
    const res = await api.get<Blob>(`/projects/${project_id}/articles/${id}/fulltext/pdf`, {
      responseType: 'blob',
    })
    // Ignore a response for an article we have already navigated away from
    if (props.article.id !== id) return
    pdfUrl.value = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
  } catch (err: unknown) {
    if (axios.isAxiosError(err) && err.response?.status === 404) pdfMissing.value = true
    else pdfError.value = 'The PDF could not be loaded.'
  } finally {
    pdfLoading.value = false
  }
}

onMounted(() => {
  if (!hasPdf.value && text.value) tab.value = 'text'
  void loadPdf()
})
onUnmounted(revokePdf)
watch(
  () => [props.article.id, props.article.full_text_path, text.value] as const,
  ([id, path], [prevId, prevPath]) => {
    if (hasPdf.value) tab.value = 'pdf'
    else if (text.value) tab.value = 'text'
    if (id !== prevId || path !== prevPath) void loadPdf()
  }
)

// --- Automatic retrieval of a single article
const retrieving = ref(false)
const retrieval = ref<FullTextRetrievalResult | null>(null)
const canRetrieve = computed(
  () => props.canUpload && props.article.status === 'awaiting_full_text' && !props.article.full_text_retrieved
)

const retrieve = async () => {
  retrieving.value = true
  retrieval.value = null
  error.value = null
  try {
    retrieval.value = await post<FullTextRetrievalResult>(
      `/projects/${props.article.project_id}/articles/${props.article.id}/retrieve-fulltext`
    )
    emit('uploaded')
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'Full-text retrieval failed')
  } finally {
    retrieving.value = false
  }
}

const statusLabel: Record<string, string> = {
  success: 'retrieved',
  not_configured: 'not configured',
  not_available: 'not available',
  error: 'error',
}

const onFile = async (event: Event) => {
  const el = event.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (!file) return
  uploading.value = true
  percent.value = 0
  message.value = null
  error.value = null
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await post<FullTextUploadResponse>(
      `/projects/${props.article.project_id}/articles/${props.article.id}/fulltext/upload`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) percent.value = Math.round((e.loaded / e.total) * 100)
        },
      }
    )
    message.value = res.text_extracted
      ? `PDF uploaded; ${res.text_length.toLocaleString()} characters of text extracted.`
      : 'PDF uploaded, but no text could be extracted (scanned document?).'
    emit('uploaded')
  } catch (err: unknown) {
    error.value = getErrorMessage(err, 'PDF upload failed')
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <Card class="p-4 space-y-3" data-testid="fulltext-panel">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <h3 class="font-semibold">Full text</h3>
        <Badge v-if="hasPdf" variant="secondary">PDF stored</Badge>
        <Badge v-else variant="outline">No PDF</Badge>
        <Badge v-if="article.full_text_source" variant="secondary" data-testid="fulltext-source">
          Source: {{ article.full_text_source }}
        </Badge>
      </div>
      <div v-if="canUpload" class="flex gap-2">
        <Button
          v-if="canRetrieve"
          size="sm"
          variant="outline"
          :disabled="retrieving"
          data-testid="retrieve-fulltext"
          @click="retrieve"
        >
          {{ retrieving ? 'Retrieving...' : 'Retrieve full text' }}
        </Button>
        <Button size="sm" variant="outline" :disabled="uploading" @click="input?.click()">
          {{ hasPdf ? 'Replace PDF' : 'Upload PDF' }}
        </Button>
        <input ref="input" type="file" accept=".pdf,application/pdf" class="hidden" data-testid="pdf-input" @change="onFile" />
      </div>
    </div>

    <Progress v-if="uploading" :value="percent" />
    <p v-if="message" class="text-sm text-green-600" role="status">{{ message }}</p>
    <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>

    <p
      v-if="article.full_text_retrieval_error && !article.full_text_retrieved"
      class="text-sm text-destructive"
      data-testid="fulltext-retrieval-error"
    >
      Last retrieval attempt failed: {{ article.full_text_retrieval_error }}
    </p>

    <div v-if="retrieval" class="rounded-md border p-3 text-sm space-y-1" data-testid="retrieval-attempts">
      <p class="font-medium">
        {{ retrieval.retrieved ? `Retrieved from ${retrieval.source}` : 'No full text found' }}
      </p>
      <ul class="space-y-0.5 text-muted-foreground">
        <li v-for="a in retrieval.attempts" :key="a.source" :data-testid="`attempt-${a.source}`">
          <span class="font-medium text-foreground">{{ a.source }}</span>: {{ statusLabel[a.status] ?? a.status }}
          <span v-if="a.detail"> ({{ a.detail }})</span>
        </li>
      </ul>
    </div>

    <div class="inline-flex rounded-md bg-muted p-1" role="tablist" aria-label="Full text view">
      <button
        v-for="t in ([['pdf', 'PDF'], ['text', 'Extracted text']] as const)"
        :key="t[0]"
        type="button"
        role="tab"
        :aria-selected="tab === t[0]"
        :data-testid="`fulltext-tab-${t[0]}`"
        :class="[
          'rounded-sm px-3 py-1 text-xs font-medium transition-all',
          tab === t[0] ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
        ]"
        @click="tab = t[0]"
      >
        {{ t[1] }}
      </button>
    </div>

    <template v-if="tab === 'pdf'">
      <p v-if="pdfLoading" class="text-sm text-muted-foreground">Loading PDF...</p>
      <iframe
        v-else-if="pdfUrl"
        :src="pdfUrl"
        title="Full-text PDF"
        class="w-full h-[70vh] rounded-md border"
        data-testid="pdf-viewer"
      />
      <p v-else-if="pdfError" class="text-sm text-destructive" role="alert">{{ pdfError }}</p>
      <p v-else-if="pdfMissing" class="text-sm text-muted-foreground" data-testid="pdf-missing">
        No PDF is stored for this article<template v-if="text">; switch to the extracted text instead</template>.
      </p>
    </template>

    <template v-else>
      <div
        v-if="text"
        :class="['overflow-y-auto rounded-md border bg-muted/40 p-3 text-sm leading-relaxed whitespace-pre-wrap break-words', heightClass]"
        tabindex="0"
        aria-label="Extracted full text"
        data-testid="fulltext-content"
      >
        {{ text }}
      </div>
      <p v-else class="text-sm text-muted-foreground">
        <template v-if="hasPdf">The PDF has no extractable text.</template>
        <template v-else>No full text has been uploaded for this article yet.</template>
      </p>
    </template>
  </Card>
</template>
