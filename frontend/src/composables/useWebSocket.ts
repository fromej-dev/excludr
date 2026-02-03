import { onMounted, onUnmounted, watch } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'
import { useAuthStore } from '@/stores/auth'
import { storeToRefs } from 'pinia'

/**
 * Composable for WebSocket integration in components.
 * Automatically connects/disconnects based on authentication state.
 */
export function useWebSocket() {
  const wsStore = useWebSocketStore()
  const authStore = useAuthStore()
  const { isAuthenticated } = storeToRefs(authStore)

  const initializeWebSocket = () => {
    const token = localStorage.getItem('excludr_token')
    if (token && isAuthenticated.value && !wsStore.isConnected) {
      wsStore.connect(token)
    }
  }

  const cleanupWebSocket = () => {
    wsStore.disconnect()
  }

  // Watch authentication state
  watch(
    isAuthenticated,
    (authenticated) => {
      if (authenticated) {
        initializeWebSocket()
      } else {
        cleanupWebSocket()
      }
    },
    { immediate: true }
  )

  onMounted(() => {
    initializeWebSocket()
  })

  onUnmounted(() => {
    cleanupWebSocket()
  })

  return {
    ...wsStore,
  }
}

/**
 * Composable for listening to WebSocket messages in components.
 */
export function useWebSocketListener(
  eventType: string,
  handler: (data: any) => void
) {
  const wsStore = useWebSocketStore()
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    unsubscribe = wsStore.onMessage(eventType, handler)
  })

  onUnmounted(() => {
    if (unsubscribe) {
      unsubscribe()
    }
  })

  return {
    unsubscribe: () => {
      if (unsubscribe) {
        unsubscribe()
        unsubscribe = null
      }
    },
  }
}

/**
 * Composable for listening to project-specific WebSocket messages.
 */
export function useProjectWebSocket(projectId: number, handler: (data: any) => void) {
  const wsStore = useWebSocketStore()
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    // Join project room
    wsStore.joinProjectRoom(projectId)

    // Listen for project-specific messages
    unsubscribe = wsStore.onMessage(`project:${projectId}`, handler)
  })

  onUnmounted(() => {
    // Leave project room
    wsStore.leaveProjectRoom(projectId)

    // Unsubscribe from messages
    if (unsubscribe) {
      unsubscribe()
    }
  })

  return {
    unsubscribe: () => {
      if (unsubscribe) {
        unsubscribe()
        unsubscribe = null
      }
    },
  }
}
