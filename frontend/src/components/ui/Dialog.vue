<script setup lang="ts">
import { ref, watch } from 'vue'
import { onClickOutside } from '@vueuse/core'

interface Props {
  open?: boolean
  title?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const dialogRef = ref<HTMLElement | null>(null)

const close = () => {
  emit('update:open', false)
}

onClickOutside(dialogRef, () => {
  if (props.open) {
    close()
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black/50" @click="close" />
        <div
          ref="dialogRef"
          class="relative z-50 w-full max-w-lg rounded-lg border bg-card p-6 shadow-lg"
        >
          <div v-if="title" class="mb-4">
            <h2 class="text-lg font-semibold">{{ title }}</h2>
          </div>
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.2s;
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}
</style>
