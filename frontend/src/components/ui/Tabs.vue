<script setup lang="ts">
import { provide, ref, computed } from 'vue'

interface Props {
  modelValue?: string
  defaultValue?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const activeTab = computed({
  get: () => props.modelValue || props.defaultValue || '',
  set: (value) => emit('update:modelValue', value),
})

provide('activeTab', activeTab)
provide('setActiveTab', (value: string) => {
  activeTab.value = value
})
</script>

<template>
  <div>
    <slot />
  </div>
</template>
