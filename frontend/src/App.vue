<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useWebSocketStore } from '@/stores/websocket'
import { storeToRefs } from 'pinia'
import ToastContainer from '@/components/ui/ToastContainer.vue'

const authStore = useAuthStore()
const wsStore = useWebSocketStore()
const { isAuthenticated } = storeToRefs(authStore)

onMounted(() => {
  authStore.initialize()
})

// Watch authentication state and manage WebSocket connection
watch(
  isAuthenticated,
  (authenticated) => {
    if (authenticated) {
      const token = localStorage.getItem('excludr_token')
      if (token) {
        wsStore.connect(token)
      }
    } else {
      wsStore.disconnect()
    }
  },
  { immediate: true }
)
</script>

<template>
  <div id="app">
    <router-view />
    <ToastContainer />
  </div>
</template>
