<script setup lang="ts">
// Renders a PDF onto canvases with pdf.js, for browsers without a built-in
// PDF viewer (Chrome on Android shows only an "Open" placeholder in an iframe).
import { ref, watch, onMounted, onUnmounted } from 'vue'
import type { PDFDocumentLoadingTask } from 'pdfjs-dist'

interface Props {
  data: Blob
  heightClass?: string
}

const props = withDefaults(defineProps<Props>(), { heightClass: 'h-[70vh]' })

const container = ref<HTMLDivElement | null>(null)
const pages = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

let task: PDFDocumentLoadingTask | null = null
let generation = 0

const destroy = () => {
  generation++
  void task?.destroy()
  task = null
  if (pages.value) pages.value.replaceChildren()
}

const render = async () => {
  destroy()
  const current = generation
  loading.value = true
  error.value = null
  try {
    const pdfjs = await import('pdfjs-dist')
    if (!pdfjs.GlobalWorkerOptions.workerSrc) {
      pdfjs.GlobalWorkerOptions.workerSrc = (await import('pdfjs-dist/build/pdf.worker.min.mjs?url')).default
    }
    const data = new Uint8Array(await props.data.arrayBuffer())
    if (current !== generation) return
    task = pdfjs.getDocument({ data })
    const doc = await task.promise
    const width = (container.value?.clientWidth ?? 600) - 2
    const ratio = window.devicePixelRatio || 1
    for (let n = 1; n <= doc.numPages; n++) {
      if (current !== generation) return
      const page = await doc.getPage(n)
      const viewport = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width })
      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(viewport.width * ratio)
      canvas.height = Math.floor(viewport.height * ratio)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`
      canvas.className = 'block bg-white mx-auto'
      canvas.setAttribute('aria-label', `Page ${n} of ${doc.numPages}`)
      pages.value?.appendChild(canvas)
      await page.render({
        canvas,
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
      }).promise
      if (n === 1) loading.value = false
    }
  } catch (err: unknown) {
    if (current === generation) error.value = 'The PDF could not be displayed.'
    console.error(err)
  } finally {
    if (current === generation) loading.value = false
  }
}

onMounted(render)
onUnmounted(destroy)
watch(() => props.data, render)
</script>

<template>
  <div
    ref="container"
    :class="['w-full overflow-y-auto rounded-md border bg-muted/40', heightClass]"
    data-testid="pdf-canvas-viewer"
  >
    <p v-if="loading" class="p-3 text-sm text-muted-foreground">Rendering PDF...</p>
    <p v-if="error" class="p-3 text-sm text-destructive" role="alert">{{ error }}</p>
    <div ref="pages" class="space-y-2" />
  </div>
</template>
