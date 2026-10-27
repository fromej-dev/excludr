<script setup lang="ts">
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type { Article, FullTextUploadResponse } from '@/types'
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

const { post } = useApi()

const input = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const percent = ref(0)
const message = ref<string | null>(null)
const error = ref<string | null>(null)

const text = computed(() => props.article.full_text_content?.trim() ?? '')
const hasPdf = computed(() => !!props.article.full_text_path)

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
      </div>
      <div v-if="canUpload">
        <Button size="sm" variant="outline" :disabled="uploading" @click="input?.click()">
          {{ hasPdf ? 'Replace PDF' : 'Upload PDF' }}
        </Button>
        <input ref="input" type="file" accept=".pdf,application/pdf" class="hidden" data-testid="pdf-input" @change="onFile" />
      </div>
    </div>

    <Progress v-if="uploading" :value="percent" />
    <p v-if="message" class="text-sm text-green-600" role="status">{{ message }}</p>
    <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>

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
    <p v-if="text" class="text-xs text-muted-foreground">
      Showing text extracted from the PDF (the original file is not served by the API).
    </p>
  </Card>
</template>
