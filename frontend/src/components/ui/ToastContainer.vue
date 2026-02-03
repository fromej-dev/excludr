<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useWebSocketStore } from '@/stores/websocket'
import Toast from './Toast.vue'

const wsStore = useWebSocketStore()
const { notifications } = storeToRefs(wsStore)

const sortedNotifications = computed(() => {
  return [...notifications.value].sort((a, b) => b.timestamp - a.timestamp)
})
</script>

<template>
  <div class="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md">
    <TransitionGroup name="toast">
      <Toast
        v-for="notification in sortedNotifications"
        :key="notification.id"
        :message="notification.message"
        :level="notification.level"
        @close="wsStore.removeNotification(notification.id)"
      />
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.toast-move {
  transition: transform 0.3s ease;
}
</style>
