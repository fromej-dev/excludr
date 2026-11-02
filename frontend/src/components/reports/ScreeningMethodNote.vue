<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'
import Button from '@/components/ui/Button.vue'

interface Props {
  text: string
}

const props = defineProps<Props>()
const wsStore = useWebSocketStore()

const quote = ref<HTMLElement | null>(null)
const copied = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

const selectText = () => {
  if (!quote.value) return
  const range = document.createRange()
  range.selectNodeContents(quote.value)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
}

const copy = async () => {
  try {
    await navigator.clipboard.writeText(props.text)
    wsStore.addNotification('Methods text copied', 'success')
    copied.value = true
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => (copied.value = false), 2000)
  } catch {
    selectText()
    wsStore.addNotification('Copy failed — the text is selected, press Ctrl+C', 'error')
  }
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <section class="mt-6 space-y-2 border-t pt-4" data-testid="screening-method">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-sm font-semibold">
        Methods text <span class="font-normal text-muted-foreground">(suggested wording)</span>
      </h3>
      <Button size="sm" variant="outline" data-testid="copy-screening-method" @click="copy">
        {{ copied ? 'Copied' : 'Copy' }}
      </Button>
    </div>
    <blockquote ref="quote" class="border-l-4 border-ai pl-3 text-sm" data-testid="prisma-screening-method">
      {{ text }}
    </blockquote>
    <p class="text-xs text-muted-foreground">
      Generated from the ranking runs and the stopping-rule application. Suggested wording: check it
      against your protocol and edit it before use.
    </p>
  </section>
</template>
